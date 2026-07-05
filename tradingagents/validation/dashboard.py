from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel

from tradingagents.agents.utils.rating import parse_rating

SAFE_RECOMMENDATION = "INSUFFICIENT_EVIDENCE"
SAFE_ACTION = "NO_CURRENT_TRANSACTION"
ACTIONABLE_STATUSES = {"verified"}


class DashboardModel(BaseModel):
    report_status: Literal["verified", "verified_with_warnings", "research_only", "blocked"]
    decision_status: Literal["available", "blocked"] = "blocked"
    recommendation: str
    action: str
    target_low: Decimal | None = None
    target_base: Decimal | None = None
    target_high: Decimal | None = None
    sentiment: str | None = None
    current_price: Decimal | None = None
    price_currency: str | None = None
    price_as_of: str | None = None
    data_quality_score: int

    def pdf_metrics(self) -> dict[str, str]:
        return {
            "Status": self.report_status.replace("_", " ").title(),
            "Decision Status": self.decision_status.replace("_", " ").title(),
            "Recommendation": self.recommendation,
            "Action": self.action,
            "Target": _format_target(self),
        }


def build_dashboard_model(final_state: dict, validation_result: Any) -> DashboardModel:
    final_decision = str(final_state.get("final_trade_decision", ""))
    status = getattr(validation_result, "status", "research_only")
    recommendation = _recommendation_for_status(status, final_decision)
    target = _extract_price_target(final_decision) if _status_allows_action(status) else None
    market_data = _as_dict(final_state.get("market_data_freshness")) or {}
    instrument = _as_dict(final_state.get("instrument_resolution")) or {}
    candidate = (instrument.get("candidates") or [{}])[0] if isinstance(instrument.get("candidates"), list) else {}

    return DashboardModel(
        report_status=status,
        decision_status=_decision_status_for_report_status(status),
        recommendation=recommendation,
        action=_action_for_status_and_rating(status, recommendation),
        target_base=target,
        sentiment=None,
        current_price=None,
        price_currency=candidate.get("currency"),
        price_as_of=market_data.get("market_data_session"),
        data_quality_score=_data_quality_score(final_state, validation_result),
    )


def validate_dashboard_consistency(final_state: dict) -> list[dict[str, str]]:
    dashboard = _as_dict(final_state.get("dashboard_model"))
    if not dashboard:
        return []

    issues: list[dict[str, str]] = []
    final_decision = str(final_state.get("final_trade_decision", ""))
    status = str(dashboard.get("report_status") or "research_only")
    final_rating = parse_rating(final_decision, default="NOT_AVAILABLE")

    if not _status_allows_action(status):
        if dashboard.get("recommendation") != SAFE_RECOMMENDATION:
            issues.append(
                {
                    "code": "RESEARCH_ONLY_ACTION_CONFLICT",
                    "location": "dashboard_model.recommendation",
                    "message": (
                        "Blocked or research-only reports must publish "
                        f"{SAFE_RECOMMENDATION}, not {dashboard.get('recommendation')}."
                    ),
                }
            )
        if dashboard.get("action") != SAFE_ACTION:
            issues.append(
                {
                    "code": "RESEARCH_ONLY_ACTION_CONFLICT",
                    "location": "dashboard_model.action",
                    "message": (
                        "Blocked or research-only reports must publish "
                        f"'{SAFE_ACTION}', not '{dashboard.get('action')}'."
                    ),
                }
            )
        if _decimal_or_none(dashboard.get("target_base")) is not None:
            issues.append(
                {
                    "code": "RESEARCH_ONLY_ACTION_CONFLICT",
                    "location": "dashboard_model.target_base",
                    "message": "Blocked or research-only reports must not publish a dashboard target.",
                }
            )
        return issues

    if dashboard.get("recommendation") != final_rating:
        issues.append(
            {
                "code": "DASHBOARD_BODY_MISMATCH",
                "location": "dashboard_model.recommendation",
                "message": (
                    "Dashboard recommendation does not match final Portfolio "
                    f"Manager rating ({dashboard.get('recommendation')} != {final_rating})."
                ),
            }
        )

    body_target = _extract_price_target(final_decision)
    dashboard_target = _decimal_or_none(dashboard.get("target_base"))
    if body_target != dashboard_target:
        issues.append(
            {
                "code": "DASHBOARD_BODY_MISMATCH",
                "location": "dashboard_model.target_base",
                "message": "Dashboard target does not match final decision price target.",
            }
        )

    return issues


def _extract_price_target(text: str) -> Decimal | None:
    patterns = (
        r"(?im)^\s*(?:\*\*)?Price Target(?:\*\*)?\s*[:\-]\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"(?im)^\s*(?:\*\*)?Target Price(?:\*\*)?\s*[:\-]\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _decimal_or_none(match.group(1))
    return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _action_for_status_and_rating(status: str, rating: str) -> str:
    if not _status_allows_action(status):
        return SAFE_ACTION
    if rating == "NOT_AVAILABLE":
        return "No final rating available"
    return f"Use final Portfolio Manager rating: {rating}"


def _recommendation_for_status(status: str, final_decision: str) -> str:
    if not _status_allows_action(status):
        return SAFE_RECOMMENDATION
    return parse_rating(final_decision, default="NOT_AVAILABLE")


def _status_allows_action(status: str) -> bool:
    return status in ACTIONABLE_STATUSES


def _decision_status_for_report_status(status: str) -> str:
    return "available" if _status_allows_action(status) else "blocked"


def _data_quality_score(final_state: dict, validation_result: Any) -> int:
    score = 100
    for issue in getattr(validation_result, "issues", []):
        severity = getattr(issue, "severity", None)
        score -= 25 if severity == "blocking" else 10

    for key in ("instrument_resolution", "market_data_freshness"):
        if not final_state.get(key):
            score -= 10

    return max(0, min(100, score))


def _format_target(model: DashboardModel) -> str:
    if model.target_low is not None or model.target_high is not None:
        low = _format_decimal(model.target_low) if model.target_low is not None else "N/A"
        high = _format_decimal(model.target_high) if model.target_high is not None else "N/A"
        return f"{low} - {high}"
    if model.target_base is not None:
        return _format_decimal(model.target_base)
    return "N/A"


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _as_dict(value: Any) -> dict | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None
