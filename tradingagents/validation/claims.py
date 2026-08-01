from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

ClaimValidationStatus = Literal[
    "pending",
    "verified",
    "unsupported",
    "contradicted",
    "invalid_calculation",
]


class DownstreamClaim(BaseModel):
    claim_id: str
    agent_name: str
    location: str
    statement: str
    claim_type: str
    supporting_ids: list[str] = Field(default_factory=list)
    requires_numeric_validation: bool = False
    requires_source_validation: bool = False
    validation_status: ClaimValidationStatus
    publishable: bool = False


def extract_downstream_claims(final_state: dict) -> list[DownstreamClaim]:
    metadata = _as_dict(final_state.get("technical_validation")) or {}
    active_metrics = _active_market_metrics(final_state)
    claims: list[DownstreamClaim] = []

    for location, text in _iter_claim_fields(final_state):
        for statement in _candidate_statements(text):
            claims.extend(
                _claims_from_statement(
                    location=location,
                    statement=statement,
                    metadata=metadata,
                    active_metrics=active_metrics,
                )
            )

    return _dedupe_claims(claims)


def verified_claims(final_state: dict) -> list[DownstreamClaim]:
    return [
        claim
        for claim in extract_downstream_claims(final_state)
        if claim.validation_status == "verified" and claim.publishable
    ]


def rejected_claims(final_state: dict) -> list[DownstreamClaim]:
    return [
        claim
        for claim in extract_downstream_claims(final_state)
        if claim.validation_status != "verified" or not claim.publishable
    ]


def _claims_from_statement(
    *,
    location: str,
    statement: str,
    metadata: dict,
    active_metrics: set[str],
) -> list[DownstreamClaim]:
    claims = []
    lower = statement.lower()

    if "bullish divergence" in lower:
        validation = _as_dict(metadata.get("rsi_divergence") or metadata.get("bullish_divergence"))
        claims.append(
            _claim(
                location,
                statement,
                "bullish_divergence",
                validated=_validated_event(validation, "bullish_divergence"),
                supporting_ids=_supporting_ids("technical_validation.rsi_divergence", validation),
                requires_numeric_validation=True,
            )
        )

    if "bearish divergence" in lower:
        validation = _as_dict(metadata.get("rsi_divergence") or metadata.get("bearish_divergence"))
        claims.append(
            _claim(
                location,
                statement,
                "bearish_divergence",
                validated=_validated_event(validation, "bearish_divergence"),
                supporting_ids=_supporting_ids("technical_validation.rsi_divergence", validation),
                requires_numeric_validation=True,
            )
        )

    cross_statement = _strip_cross_context_language(statement)

    if re.search(r"\bgolden cross\b", cross_statement, re.IGNORECASE):
        cross = _as_dict(metadata.get("moving_average_cross")) or {}
        claims.append(
            _claim(
                location,
                statement,
                "moving_average_cross",
                validated=cross.get("event") == "golden_cross" and bool(cross.get("event_date")),
                supporting_ids=_supporting_ids("technical_validation.moving_average_cross", cross),
                requires_numeric_validation=True,
            )
        )

    if re.search(r"\bdeath cross\b", cross_statement, re.IGNORECASE):
        cross = _as_dict(metadata.get("moving_average_cross")) or {}
        claims.append(
            _claim(
                location,
                statement,
                "moving_average_cross",
                validated=cross.get("event") == "death_cross" and bool(cross.get("event_date")),
                supporting_ids=_supporting_ids("technical_validation.moving_average_cross", cross),
                requires_numeric_validation=True,
            )
        )

    if re.search(r"\bbollinger\s+squeeze\b", statement, re.IGNORECASE):
        squeeze = _as_dict(metadata.get("bollinger_squeeze")) or {}
        claims.append(
            _claim(
                location,
                statement,
                "bollinger_squeeze",
                validated=squeeze.get("validated") is True,
                supporting_ids=_supporting_ids("technical_validation.bollinger_squeeze", squeeze),
                requires_numeric_validation=True,
            )
        )

    if re.search(r"\bVWMA\b|volume[-\s]?weighted moving average", statement, re.IGNORECASE):
        claims.append(
            _claim(
                location,
                statement,
                "technical_metric_reference",
                validated="VWMA" in active_metrics,
                supporting_ids=["report:market_report"] if "VWMA" in active_metrics else [],
                requires_source_validation=True,
            )
        )

    if re.search(
        r"(?i)\b(institutional (?:buying|selling|accumulation|distribution)|"
        r"smart money|seller exhaustion|buyer exhaustion|accumulation by funds|"
        r"distribution by funds|accumulation behavior|distribution behavior|"
        r"buyers stepping in|funds building positions)\b",
        statement,
    ):
        volume = _as_dict(metadata.get("volume_inference")) or {}
        claims.append(
            _claim(
                location,
                statement,
                "volume_flow_inference",
                validated=volume.get("validated") is True,
                supporting_ids=_supporting_ids("technical_validation.volume_inference", volume),
                requires_source_validation=True,
            )
        )

    if re.search(
        r"(?i)\b(consecutive|every session|straight sessions?|continuously expanding|"
        r"expanded for \d+|expanding for \d+|streak)\b",
        statement,
    ):
        support = _streak_supporting_ids(metadata)
        claims.append(
            _claim(
                location,
                statement,
                "sequence_streak",
                validated=bool(support),
                supporting_ids=support,
                requires_numeric_validation=True,
            )
        )

    return claims


def _claim(
    location: str,
    statement: str,
    claim_type: str,
    *,
    validated: bool,
    supporting_ids: list[str],
    requires_numeric_validation: bool = False,
    requires_source_validation: bool = False,
) -> DownstreamClaim:
    status: ClaimValidationStatus = "verified" if validated else "unsupported"
    return DownstreamClaim(
        claim_id=_claim_id(location, statement, claim_type),
        agent_name=_agent_name(location),
        location=location,
        statement=statement,
        claim_type=claim_type,
        supporting_ids=supporting_ids,
        requires_numeric_validation=requires_numeric_validation,
        requires_source_validation=requires_source_validation,
        validation_status=status,
        publishable=validated,
    )


def _candidate_statements(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+|(?:^|\s)[-*]\s+", normalized)
    return [part.strip(" -") for part in parts if part.strip(" -")]


def _strip_cross_context_language(text: str) -> str:
    cleaned = re.sub(
        r"(?i)\b(?:golden\s*/\s*death|golden\s+or\s+death|golden|death)\s+cross\s+"
        r"(?:context|setups?|watchlist|reference)\b",
        "",
        text,
    )
    cleaned = re.sub(
        r"(?i)\b(?:approaching|precedes|preceding|compressing|on the)\s+(?:a\s+)?"
        r"(?:golden|death)\s+cross\b",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\b(?:golden|death)\s+cross\s+(?:approaching|approaches|compressing|"
        r"formation|formations|argument|debate|being)\b",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\bhistorically precedes\s+(?:golden|death)\s+cross\s+formations\b",
        "",
        cleaned,
    )
    return cleaned


def _iter_claim_fields(final_state: dict) -> list[tuple[str, str]]:
    fields = [
        (key, str(final_state.get(key, "")))
        for key in (
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "supply_chain_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
        )
    ]

    debate = final_state.get("investment_debate_state") or {}
    if isinstance(debate, dict):
        for key in ("bull_history", "bear_history", "judge_decision"):
            fields.append((f"investment_debate_state.{key}", str(debate.get(key, ""))))

    risk = final_state.get("risk_debate_state") or {}
    if isinstance(risk, dict):
        for key in (
            "aggressive_history",
            "conservative_history",
            "neutral_history",
            "judge_decision",
        ):
            fields.append((f"risk_debate_state.{key}", str(risk.get(key, ""))))

    return fields


def _active_market_metrics(final_state: dict) -> set[str]:
    market_report = str(final_state.get("market_report", ""))
    metrics = set()
    if re.search(r"\bVWMA\b|volume[-\s]?weighted moving average", market_report, re.IGNORECASE):
        metrics.add("VWMA")
    return metrics


def _validated_event(validation: dict | None, expected_event: str) -> bool:
    if not validation:
        return False
    if validation.get("validated") is not True:
        return False
    return validation.get("event") in (None, expected_event)


def _supporting_ids(source_id: str, validation: dict | None) -> list[str]:
    if not validation:
        return []
    if validation.get("validated") is True or validation.get("event_date"):
        return [source_id]
    return []


def _streak_supporting_ids(metadata: dict) -> list[str]:
    ids = []
    for key in (
        "streak_calculations",
        "calculation_ids",
        "macd_histogram_streak",
        "sequence_calculations",
    ):
        value = metadata.get(key)
        if value:
            ids.append(f"technical_validation.{key}")
    return ids


def _dedupe_claims(claims: list[DownstreamClaim]) -> list[DownstreamClaim]:
    seen = set()
    deduped = []
    for claim in claims:
        if claim.claim_id in seen:
            continue
        seen.add(claim.claim_id)
        deduped.append(claim)
    return deduped


def _claim_id(location: str, statement: str, claim_type: str) -> str:
    digest = hashlib.sha1(f"{location}|{claim_type}|{statement}".encode()).hexdigest()
    return f"claim:{digest[:16]}"


def _agent_name(location: str) -> str:
    if location.startswith("investment_debate_state.bull"):
        return "bull_researcher"
    if location.startswith("investment_debate_state.bear"):
        return "bear_researcher"
    if location.startswith("investment_debate_state"):
        return "research_manager"
    if location.startswith("risk_debate_state.aggressive"):
        return "aggressive_risk_analyst"
    if location.startswith("risk_debate_state.conservative"):
        return "conservative_risk_analyst"
    if location.startswith("risk_debate_state.neutral"):
        return "neutral_risk_analyst"
    if location.startswith("risk_debate_state"):
        return "portfolio_manager"
    if location == "trader_investment_plan":
        return "trader"
    if location == "final_trade_decision":
        return "portfolio_manager"
    return location.replace("_report", "_analyst")


def _as_dict(value: Any) -> dict | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None
