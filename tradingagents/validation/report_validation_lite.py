"""Deterministic report-validation-lite for Golden Trend (no LLM, no full report)."""

from __future__ import annotations

from typing import Any


def validate_report_lite(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol") or "").upper()
    raw_signal = str(payload.get("rawSignal") or payload.get("raw_signal") or "NO_SIGNAL").upper()
    final_signal = str(payload.get("finalSignal") or payload.get("final_signal") or "NO_SIGNAL").upper()
    trade_allowed = bool(payload.get("tradeAllowed") if "tradeAllowed" in payload else payload.get("trade_allowed"))
    confidence = int(payload.get("confidenceScore") or payload.get("confidence_score") or 0)
    blockers = _as_list(payload.get("topBlockers") or payload.get("top_blockers"))
    flags = _as_list(payload.get("flags"))
    supply_chain = payload.get("supplyChainContext") or payload.get("supply_chain_context") or {}

    direction = _direction_from_signal(raw_signal)
    hard_block_count = len(blockers) + len([flag for flag in flags if _is_hard_flag(flag)])

    warnings: list[str] = []
    supporting: list[str] = []
    contradicting: list[str] = []

    if supply_chain.get("has_graph_coverage") is False:
        warnings.append("Supply-chain context has no graph coverage for this symbol.")
    elif supply_chain.get("chokepoints"):
        supporting.append("Supply-chain chokepoints available for contextual review.")

    if final_signal in {"BLOCKED", "NO_SIGNAL"} or hard_block_count >= 4:
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="BLOCKED",
            recommendation="INSUFFICIENT_EVIDENCE",
            directional_bias="MIXED",
            confidence=0.2,
            hard_blocks=blockers or flags[:8],
            warnings=warnings,
            supporting=supporting,
            contradicting=contradicting,
            summary="Report validation blocked because signal-service hard blockers remain unresolved.",
        )

    if final_signal == "WATCHLIST_ONLY" or not trade_allowed:
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="BLOCKED",
            recommendation="INSUFFICIENT_EVIDENCE",
            directional_bias="MIXED",
            confidence=0.35,
            hard_blocks=blockers or flags[:8],
            warnings=warnings or ["Signal service returned watchlist-only posture."],
            supporting=supporting,
            contradicting=contradicting,
            summary="Setup remains watchlist-only; report context cannot upgrade this to a trade candidate.",
        )

    if confidence < 65:
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="MIXED",
            recommendation="INSUFFICIENT_EVIDENCE",
            directional_bias="MIXED",
            confidence=0.45,
            hard_blocks=[],
            warnings=warnings + ["Signal confidence below reduced-size threshold."],
            supporting=supporting,
            contradicting=contradicting,
            summary="Signal is directionally active but confidence is too low for report approval.",
        )

    directional_bias = _directional_bias(raw_signal)
    return _wrap(
        symbol=symbol,
        direction=direction,
        status="APPROVED",
        recommendation="APPROVED",
        directional_bias=directional_bias,
        confidence=min(0.85, 0.55 + confidence / 200),
        hard_blocks=[],
        warnings=warnings,
        supporting=supporting or ["Signal-service gates passed minimum execution thresholds."],
        contradicting=contradicting,
        summary="Report validation does not contradict the signal-service setup.",
    )


def _wrap(
    *,
    symbol: str,
    direction: str,
    status: str,
    recommendation: str,
    directional_bias: str,
    confidence: float,
    hard_blocks: list[str],
    warnings: list[str],
    supporting: list[str],
    contradicting: list[str],
    summary: str,
) -> dict[str, Any]:
    report_validation = {
        "symbol": symbol,
        "direction": direction,
        "status": status,
        "recommendation": recommendation,
        "directionalBias": directional_bias,
        "confidence": round(confidence, 3),
        "hardBlocks": hard_blocks,
        "warnings": warnings,
        "supportingPoints": supporting,
        "contradictingPoints": contradicting,
        "summary": summary,
        "dataQuality": "partial",
    }
    return {"reportValidation": report_validation, **report_validation}


def _direction_from_signal(raw_signal: str) -> str:
    if raw_signal == "ENTER_LONG":
        return "LONG"
    if raw_signal == "ENTER_SHORT":
        return "SHORT"
    return "NONE"


def _directional_bias(raw_signal: str) -> str:
    if raw_signal == "ENTER_LONG":
        return "BULLISH"
    if raw_signal == "ENTER_SHORT":
        return "BEARISH"
    return "MIXED"


def _is_hard_flag(flag: str) -> bool:
    hard_prefixes = (
        "PROPOSAL_GATE",
        "TECHNICAL_PERMISSION",
        "STRUCTURE_MISALIGNED",
        "REGIME_PERMISSION",
        "POOR_REWARD",
        "DATA_QUALITY_BLOCKED",
        "ZERO_COST",
    )
    upper = str(flag).upper()
    return any(token in upper for token in hard_prefixes)


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]
