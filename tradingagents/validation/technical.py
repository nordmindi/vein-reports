from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

from .models import ValidationIssue

CrossEvent = Literal["golden_cross", "death_cross", "no_new_cross"]


def bullish_divergence(
    price_low_1: float,
    price_low_2: float,
    indicator_low_1: float,
    indicator_low_2: float,
) -> bool:
    return price_low_2 < price_low_1 and indicator_low_2 > indicator_low_1


def bearish_divergence(
    price_high_1: float,
    price_high_2: float,
    indicator_high_1: float,
    indicator_high_2: float,
) -> bool:
    return price_high_2 > price_high_1 and indicator_high_2 < indicator_high_1


def detect_cross(
    short_series: Sequence[float],
    long_series: Sequence[float],
    dates: Sequence[str | date] | None = None,
) -> dict[str, Any]:
    if len(short_series) < 2 or len(long_series) < 2:
        raise ValueError("At least two observations are required to detect a crossover")

    previous_diff = float(short_series[-2]) - float(long_series[-2])
    current_diff = float(short_series[-1]) - float(long_series[-1])

    if previous_diff <= 0 < current_diff:
        event: CrossEvent = "golden_cross"
    elif previous_diff >= 0 > current_diff:
        event = "death_cross"
    else:
        event = "no_new_cross"

    event_date = None
    if event != "no_new_cross" and dates:
        event_date = str(dates[-1])

    return {"event": event, "event_date": event_date}


def macd_components_reconcile(
    macd_line: float,
    signal_line: float,
    histogram: float,
    *,
    tolerance: float = 1e-6,
) -> bool:
    return math.isclose(
        float(histogram),
        float(macd_line) - float(signal_line),
        rel_tol=tolerance,
        abs_tol=tolerance,
    )


def bollinger_squeeze_valid(
    *,
    upper_band: float | None,
    middle_band: float | None,
    lower_band: float | None,
    width_percentile: float | None,
    threshold: float,
) -> bool:
    if upper_band is None or middle_band in (None, 0) or lower_band is None:
        return False
    if width_percentile is None:
        return False
    width = (float(upper_band) - float(lower_band)) / float(middle_band)
    return width >= 0 and float(width_percentile) <= float(threshold)


def validate_technical_claims(final_state: dict) -> list[ValidationIssue]:
    metadata = _as_dict(final_state.get("technical_validation")) or {}

    issues: list[ValidationIssue] = []
    for location, text in _iter_technical_claim_fields(final_state):
        issues.extend(_validate_divergence_claims(text, metadata, location))
        issues.extend(_validate_moving_average_claims(text, metadata, location))
        issues.extend(_validate_bollinger_claims(text, metadata, location))
        issues.extend(_validate_atr_claims(text, location))
        issues.extend(_validate_volume_inference_claims(text, metadata, location))
    issues.extend(_validate_macd_metadata(metadata))
    issues.extend(_validate_bollinger_metadata(metadata))
    return issues


def _validate_divergence_claims(text: str, metadata: dict, location: str) -> list[ValidationIssue]:
    claims = []
    lower_text = text.lower()

    if "bullish divergence" in lower_text:
        validation = _as_dict(metadata.get("rsi_divergence") or metadata.get("bullish_divergence"))
        if not _validated_event(validation, "bullish_divergence"):
            claims.append(
                ValidationIssue(
                    code="FALSE_BULLISH_DIVERGENCE_CLAIM",
                    severity="blocking",
                    location=location,
                    message=(
                        "Report claims bullish divergence without validated "
                        "price and indicator swing lows."
                    ),
                )
            )

    if "bearish divergence" in lower_text:
        validation = _as_dict(metadata.get("rsi_divergence") or metadata.get("bearish_divergence"))
        if not _validated_event(validation, "bearish_divergence"):
            claims.append(
                ValidationIssue(
                    code="FALSE_BEARISH_DIVERGENCE_CLAIM",
                    severity="blocking",
                    location=location,
                    message=(
                        "Report claims bearish divergence without validated "
                        "price and indicator swing highs."
                    ),
                )
            )

    return claims


def _validate_moving_average_claims(text: str, metadata: dict, location: str) -> list[ValidationIssue]:
    lower_text = _strip_cross_context_language(text).lower()
    issues = []
    cross = _as_dict(metadata.get("moving_average_cross")) or {}

    if "golden cross" in lower_text and not _cross_matches(cross, "golden_cross"):
        issues.append(
            ValidationIssue(
                code="MOVING_AVERAGE_CROSS_UNPROVEN",
                severity="blocking",
                location=location,
                message="Golden cross claim lacks a dated code-detected crossover event.",
            )
        )

    if "death cross" in lower_text and not _cross_matches(cross, "death_cross"):
        issues.append(
            ValidationIssue(
                code="MOVING_AVERAGE_CROSS_UNPROVEN",
                severity="blocking",
                location=location,
                message="Death cross claim lacks a dated code-detected crossover event.",
            )
        )

    return issues


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


def _validate_bollinger_claims(text: str, metadata: dict, location: str) -> list[ValidationIssue]:
    if not re.search(r"\bbollinger\s+squeeze\b", text, re.IGNORECASE):
        return []

    squeeze = _as_dict(metadata.get("bollinger_squeeze")) or {}
    if squeeze.get("validated") is True:
        return []

    return [
        ValidationIssue(
            code="BOLLINGER_SQUEEZE_UNPROVEN",
            severity="blocking",
            location=location,
            message="Bollinger squeeze claim lacks complete band-width validation.",
        )
    ]


def _validate_atr_claims(text: str, location: str) -> list[ValidationIssue]:
    if not re.search(r"\b(?:optimal|optimized|recommended)\s+stop\b.*\batr\b", text, re.IGNORECASE):
        return []

    return [
        ValidationIssue(
            code="ATR_SIZING_LOGIC_ERROR",
            severity="blocking",
            location=location,
            message="ATR stop claim is presented as optimized without full risk context.",
        )
    ]


def _validate_volume_inference_claims(
    text: str,
    metadata: dict,
    location: str,
) -> list[ValidationIssue]:
    if not _has_volume_inference_claim(text):
        return []

    validation = _as_dict(metadata.get("volume_inference")) or {}
    if validation.get("validated") is True:
        return []

    return [
        ValidationIssue(
            code="UNSUPPORTED_VOLUME_INFERENCE",
            severity="blocking",
            location=location,
            message="Volume-based ownership-flow inference lacks structured validation.",
        )
    ]


def _validate_macd_metadata(metadata: dict) -> list[ValidationIssue]:
    macd = _as_dict(metadata.get("macd"))
    if not macd:
        return []

    required = ("macd_line", "signal_line", "histogram")
    if not all(key in macd for key in required):
        return [
            ValidationIssue(
                code="MACD_COMPONENT_MISMATCH",
                severity="blocking",
                location="technical_validation.macd",
                message="MACD metadata must include macd_line, signal_line, and histogram.",
            )
        ]

    tolerance = float(macd.get("tolerance", 1e-6))
    if macd_components_reconcile(
        macd["macd_line"],
        macd["signal_line"],
        macd["histogram"],
        tolerance=tolerance,
    ):
        return []

    return [
        ValidationIssue(
            code="MACD_COMPONENT_MISMATCH",
            severity="blocking",
            location="technical_validation.macd",
            message="MACD histogram does not equal macd_line - signal_line.",
        )
    ]


def _validate_bollinger_metadata(metadata: dict) -> list[ValidationIssue]:
    squeeze = _as_dict(metadata.get("bollinger_squeeze"))
    if not squeeze or squeeze.get("validated") is not True:
        return []

    valid = bollinger_squeeze_valid(
        upper_band=squeeze.get("upper_band"),
        middle_band=squeeze.get("middle_band"),
        lower_band=squeeze.get("lower_band"),
        width_percentile=squeeze.get("width_percentile"),
        threshold=float(squeeze.get("threshold", 0.15)),
    )
    if valid:
        return []

    return [
        ValidationIssue(
            code="BOLLINGER_SQUEEZE_UNPROVEN",
            severity="blocking",
            location="technical_validation.bollinger_squeeze",
            message="Bollinger squeeze metadata is marked validated but components are incomplete or invalid.",
        )
    ]


def _validated_event(validation: dict | None, expected_event: str) -> bool:
    if not validation:
        return False
    if validation.get("validated") is not True:
        return False
    return validation.get("event") in (None, expected_event)


def _cross_matches(cross: dict, event: str) -> bool:
    return cross.get("event") == event and bool(cross.get("event_date"))


_VOLUME_INFERENCE_RE = re.compile(
    r"(?i)\b(institutional (?:buying|selling|accumulation|distribution)|"
    r"smart money|seller exhaustion|buyer exhaustion|accumulation by funds|"
    r"distribution by funds|accumulation behavior|distribution behavior|"
    r"buyers stepping in|funds building positions)\b"
)


def _has_volume_inference_claim(text: str) -> bool:
    for match in _VOLUME_INFERENCE_RE.finditer(text):
        prefix = text[max(0, match.start() - 40) : match.start()]
        if re.search(
            r"(?i)\b(?:no|not|without|lack(?:s|ing)?|unconfirmed|denied|absence of)\s+\w*\s*$",
            prefix,
        ):
            continue
        return True
    return False


def _as_dict(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None


def _iter_technical_claim_fields(final_state: dict) -> list[tuple[str, str]]:
    fields = [
        (key, str(final_state.get(key, "")))
        for key in (
            "market_report",
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
