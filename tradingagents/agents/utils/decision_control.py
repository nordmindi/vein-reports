from __future__ import annotations

from typing import Any


def decision_permitted(state: dict[str, Any]) -> bool:
    permission = state.get("decision_permission") or {}
    if isinstance(permission, dict) and "decision_permitted" in permission:
        return bool(permission.get("decision_permitted"))
    return True


def blocking_issue_codes(state: dict[str, Any]) -> list[str]:
    permission = state.get("decision_permission") or {}
    if not isinstance(permission, dict):
        return []
    codes = permission.get("blocking_issue_codes") or []
    return [str(code) for code in codes if str(code).strip()]


def blocking_summary(state: dict[str, Any]) -> str:
    codes = blocking_issue_codes(state)
    if not codes:
        return "Global validation has not permitted transaction authority."
    return "Global validation blocks transaction authority: " + ", ".join(codes) + "."


def diagnostic_mode(state: dict[str, Any]) -> bool:
    return not decision_permitted(state) or state.get("risk_agent_mode") == "diagnostic"
