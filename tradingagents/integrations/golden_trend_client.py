"""HTTP client for Golden Trend / Vein Signals analyze API (no hard dependency)."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

EXECUTABLE_FINALS = frozenset(
    {
        "ENTER_LONG",
        "ENTER_SHORT",
        "ENTER_LONG_REDUCED_SIZE",
        "ENTER_SHORT_REDUCED_SIZE",
    }
)


def is_golden_trend_enabled() -> bool:
    raw = os.getenv("TRADINGAGENTS_GOLDEN_TREND_ENABLED", "0").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(_base_url())


def _base_url() -> str:
    return os.getenv("TRADINGAGENTS_GOLDEN_TREND_BASE_URL", "").strip().rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.getenv("TRADINGAGENTS_GOLDEN_TREND_API_KEY", "").strip()
    if key:
        headers["X-API-Key"] = key
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _strategy_id() -> str:
    return os.getenv("TRADINGAGENTS_GOLDEN_TREND_STRATEGY_ID", "golden-trend-balanced").strip()


def analyze_symbol(
    symbol: str,
    *,
    strategy_id: str | None = None,
    timeout_seconds: float = 60.0,
) -> dict[str, Any] | None:
    base = _base_url()
    if not base:
        return None

    payload = {
        "symbols": [symbol.strip().upper()],
        "strategy": strategy_id or _strategy_id(),
        "mode": "check-only",
    }
    try:
        response = requests.post(
            f"{base}/api/v1/signals/analyze",
            json=payload,
            headers=_headers(),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Golden Trend analyze failed for %s: %s", symbol, exc)
        return None

    if not isinstance(body, dict):
        return None
    return body


def pick_primary_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    for item in results:
        if isinstance(item, dict) and item.get("status") != "error":
            return item
    first = results[0]
    return first if isinstance(first, dict) else None


def normalize_signal_result(result: dict[str, Any]) -> dict[str, Any]:
    validation = result.get("validation") or {}
    flags = list(validation.get("flags") or [])
    combined = result.get("combinedDecision") or result.get("combined_decision") or {}
    audit = result.get("decisionAudit") or result.get("decision_audit") or {}
    watchlist = result.get("watchlistConditions") or result.get("watchlist_conditions") or []

    raw_signal = str(result.get("rawSignal") or result.get("raw_signal") or "NO_SIGNAL")
    final_signal = str(
        combined.get("finalDecision")
        or result.get("finalSignal")
        or result.get("final_signal")
        or "NO_SIGNAL"
    )
    trade_allowed = bool(
        combined.get("tradeAllowed")
        if combined
        else result.get("tradeAllowed", result.get("trade_allowed"))
    )

    return {
        "symbol": str(result.get("asset") or result.get("symbol") or ""),
        "strategy": str(result.get("strategy") or result.get("strategyId") or ""),
        "rawSignal": raw_signal,
        "finalSignal": final_signal,
        "signalServiceFinal": str(
            result.get("signalServiceFinal")
            or result.get("primaryFinalSignal")
            or result.get("finalSignal")
            or final_signal
        ),
        "tradeAllowed": trade_allowed,
        "confidenceScore": int(result.get("confidenceScore") or result.get("confidence_score") or 0),
        "confidenceGrade": str(result.get("confidenceGrade") or result.get("confidence_grade") or "F"),
        "flags": flags,
        "hardBlocks": list(audit.get("hardBlocks") or audit.get("hard_blocks") or []),
        "softBlocks": list(audit.get("softBlocks") or audit.get("soft_blocks") or []),
        "warnings": list(audit.get("warnings") or []),
        "watchlistConditions": watchlist,
        "combinedDecision": combined,
        "reportValidationInput": result.get("reportValidationInput")
        or result.get("report_validation_input"),
        "tradePlan": result.get("tradePlan") or result.get("trade_plan") or {},
        "executable": final_signal in EXECUTABLE_FINALS and trade_allowed,
        "blocksTradePublication": not trade_allowed
        or final_signal in {"WATCHLIST_ONLY", "BLOCKED", "WAIT_FOR_CONFIRMATION"},
        "sourceStatus": str(result.get("status") or "ok"),
    }


def fetch_signal_validation(
    symbol: str,
    *,
    strategy_id: str | None = None,
) -> dict[str, Any] | None:
    if not is_golden_trend_enabled():
        return None
    payload = analyze_symbol(symbol, strategy_id=strategy_id)
    if not payload:
        return None
    primary = pick_primary_result(payload)
    if not primary:
        return None
    normalized = normalize_signal_result(primary)
    normalized["fetchedAt"] = payload.get("generatedAt") or payload.get("timestamp")
    return normalized
