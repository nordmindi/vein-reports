from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .claims import verified_claims


LessonValidationStatus = Literal[
    "validated",
    "invalid",
    "possible_leakage",
    "duplicate",
]


class HistoricalLesson(BaseModel):
    lesson_id: str
    ticker: str
    original_run_id: str
    original_decision_timestamp: datetime
    recommendation: str
    entry_timestamp: datetime
    entry_price: Decimal
    exit_timestamp: datetime
    exit_price: Decimal
    benchmark_symbol: str
    benchmark_entry: Decimal
    benchmark_exit: Decimal
    gross_return: Decimal
    net_return: Decimal
    benchmark_return: Decimal
    alpha: Decimal
    holding_period_sessions: int
    transaction_cost_assumption_bps: Decimal
    slippage_assumption_bps: Decimal
    pattern_features: dict[str, Decimal | str | bool] = Field(default_factory=dict)
    outcome_known_after_decision: bool
    out_of_sample: bool
    duplicate_group_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    validation_status: LessonValidationStatus


class DecisionEvidenceBundle(BaseModel):
    canonical_fact_ids: list[str] = Field(default_factory=list)
    verified_claim_ids: list[str] = Field(default_factory=list)
    validated_metric_ids: list[str] = Field(default_factory=list)
    validated_lesson_ids: list[str] = Field(default_factory=list)
    valuation_model_id: str | None = None
    unresolved_blocking_issues: list[str] = Field(default_factory=list)


def build_decision_evidence_bundle(
    final_state: dict,
    validation_result: Any | None = None,
) -> DecisionEvidenceBundle:
    blockers = []
    if validation_result is not None:
        blockers = [
            issue.code
            for issue in getattr(validation_result, "issues", [])
            if getattr(issue, "severity", None) == "blocking"
        ]

    return DecisionEvidenceBundle(
        canonical_fact_ids=_canonical_fact_ids(final_state),
        verified_claim_ids=_verified_claim_ids(final_state),
        validated_metric_ids=_validated_metric_ids(final_state),
        validated_lesson_ids=[lesson.lesson_id for lesson in usable_historical_lessons(final_state)],
        valuation_model_id=_valuation_model_id(final_state),
        unresolved_blocking_issues=sorted(set(blockers)),
    )


def usable_historical_lessons(final_state: dict) -> list[HistoricalLesson]:
    lessons = _raw_lessons(final_state)
    parsed: list[HistoricalLesson] = []
    for item in lessons:
        try:
            lesson = HistoricalLesson.model_validate(item)
        except ValidationError:
            continue
        if _lesson_is_usable(lesson):
            parsed.append(lesson)

    duplicate_groups = [
        lesson.duplicate_group_id for lesson in parsed if lesson.duplicate_group_id
    ]
    duplicated = {
        group for group in duplicate_groups if duplicate_groups.count(group) > 1
    }
    if not duplicated:
        return parsed
    return [
        lesson
        for lesson in parsed
        if not lesson.duplicate_group_id or lesson.duplicate_group_id not in duplicated
    ]


def lesson_is_usable(value: dict) -> bool:
    try:
        lesson = HistoricalLesson.model_validate(value)
    except ValidationError:
        return False
    return _lesson_is_usable(lesson)


def _lesson_is_usable(lesson: HistoricalLesson) -> bool:
    return (
        lesson.validation_status == "validated"
        and lesson.out_of_sample is True
        and lesson.outcome_known_after_decision is True
        and lesson.holding_period_sessions > 0
        and bool(lesson.original_run_id)
        and bool(lesson.source_ids)
    )


def _raw_lessons(final_state: dict) -> list[dict]:
    value = (
        final_state.get("historical_lessons_evidence")
        or final_state.get("validated_lessons")
        or final_state.get("auditable_lessons")
        or []
    )
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _canonical_fact_ids(final_state: dict) -> list[str]:
    ids = []
    for key in (
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "supply_chain_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    ):
        if str(final_state.get(key, "")).strip():
            ids.append(f"report:{key}")

    for key in ("instrument_resolution", "market_data_freshness", "news_retrieval", "vein_context_bundle"):
        if final_state.get(key):
            ids.append(f"metadata:{key}")

    return ids


def _verified_claim_ids(final_state: dict) -> list[str]:
    claims = final_state.get("verified_claims") or []
    if not isinstance(claims, list) or not claims:
        return [claim.claim_id for claim in verified_claims(final_state)]
    ids = []
    for claim in claims:
        if isinstance(claim, dict) and claim.get("validation_status") == "verified":
            claim_id = claim.get("claim_id")
            if claim_id:
                ids.append(str(claim_id))
    return ids


def _validated_metric_ids(final_state: dict) -> list[str]:
    technical = final_state.get("technical_validation") or {}
    if hasattr(technical, "model_dump"):
        technical = technical.model_dump(mode="json")
    if not isinstance(technical, dict):
        return []

    ids = []
    for key, value in technical.items():
        if isinstance(value, dict):
            if value.get("validated") is True or value.get("event_date"):
                ids.append(f"metric:{key}")
        elif isinstance(value, list) and value:
            ids.append(f"metric:{key}")
    return ids


def _valuation_model_id(final_state: dict) -> str | None:
    text = str(final_state.get("final_trade_decision", ""))
    has_target = re.search(
        r"(?im)^\s*(?:\*\*)?(?:price\s+target|target\s+price)(?:\*\*)?\s*[:\-]\s*\$?[0-9]",
        text,
    )
    has_method = re.search(
        r"(?im)^\s*(?:\*\*)?(?:valuation\s+method|methodology|valuation)(?:\*\*)?\s*[:\-]\s*\S",
        text,
    )
    if has_target and has_method:
        return "valuation:final_trade_decision"
    return None
