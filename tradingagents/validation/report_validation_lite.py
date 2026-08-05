"""Deterministic report-validation-lite for Vein Signals (no LLM, no full report).

Loose coupling: this endpoint evaluates *report-side* context only. It must not
re-litigate Vein Signals technical gates (confidence, watchlist, structure).
When Signals already blocked/watchlisted, return DEFER_TO_SIGNALS. When no
independent report evidence is available, return NO_CONTEXT so Signals can
proceed on its own strength.
"""

from __future__ import annotations

from typing import Any


def validate_report_lite(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol") or "").upper()
    raw_signal = str(payload.get("rawSignal") or payload.get("raw_signal") or "NO_SIGNAL").upper()
    final_signal = str(payload.get("finalSignal") or payload.get("final_signal") or "NO_SIGNAL").upper()
    trade_allowed = bool(
        payload.get("tradeAllowed") if "tradeAllowed" in payload else payload.get("trade_allowed")
    )
    supply_chain = payload.get("supplyChainContext") or payload.get("supply_chain_context") or {}
    intelligence = payload.get("intelligenceBrief") or payload.get("intelligence_brief") or {}
    cached = payload.get("reportContext") or payload.get("report_context") or {}

    direction = _direction_from_signal(raw_signal)
    warnings: list[str] = []
    supporting: list[str] = []
    contradicting: list[str] = []

    # Signals owns technical tradability — do not re-block on its gates.
    if final_signal in {"BLOCKED", "NO_SIGNAL"} or (
        final_signal == "WATCHLIST_ONLY" and not trade_allowed
    ):
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="DEFERRED",
            recommendation="DEFER_TO_SIGNALS",
            directional_bias="MIXED",
            confidence=0.0,
            hard_blocks=[],
            warnings=warnings,
            supporting=supporting,
            contradicting=contradicting,
            summary="Vein Signals already non-tradeable; Vein Reports defers without adding blockers.",
            data_quality="n/a",
        )

    _collect_supply_chain_evidence(supply_chain, supporting, contradicting, warnings)
    _collect_intelligence_evidence(intelligence, supporting, contradicting, warnings)
    _collect_cached_report_evidence(cached, raw_signal, supporting, contradicting, warnings)

    has_independent_context = bool(supporting or contradicting or warnings)

    if not has_independent_context:
        # Fail-open: no report-side evidence → Signals proceeds on technical strength.
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="NO_CONTEXT",
            recommendation="NEUTRAL",
            directional_bias="MIXED",
            confidence=0.5,
            hard_blocks=[],
            warnings=["No independent Vein Reports context available for this symbol."],
            supporting=[],
            contradicting=[],
            summary="No report-side context; Vein Signals decision stands unchanged.",
            data_quality="none",
        )

    hard_blocks = [item for item in contradicting if item.startswith("HARD:")]
    soft_contradictions = [item for item in contradicting if not item.startswith("HARD:")]
    clean_contradicting = [item.removeprefix("HARD:") for item in contradicting]

    if hard_blocks:
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="BLOCKED",
            recommendation="INSUFFICIENT_EVIDENCE",
            directional_bias="MIXED",
            confidence=0.25,
            hard_blocks=[item.removeprefix("HARD:") for item in hard_blocks],
            warnings=warnings,
            supporting=supporting,
            contradicting=clean_contradicting,
            summary="Vein Reports contextual risk blocks execution.",
            data_quality="partial",
        )

    bias = _infer_bias(raw_signal, supporting, soft_contradictions)
    if soft_contradictions and not supporting:
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="MIXED",
            recommendation="CAUTION",
            directional_bias=bias,
            confidence=0.4,
            hard_blocks=[],
            warnings=warnings,
            supporting=supporting,
            contradicting=clean_contradicting,
            summary="Vein Reports context conflicts with the setup; prefer reduced size or watchlist.",
            data_quality="partial",
        )

    if supporting and not soft_contradictions:
        return _wrap(
            symbol=symbol,
            direction=direction,
            status="APPROVED",
            recommendation="APPROVED",
            directional_bias=bias if bias != "MIXED" else _directional_bias(raw_signal),
            confidence=0.75,
            hard_blocks=[],
            warnings=warnings,
            supporting=supporting,
            contradicting=clean_contradicting,
            summary="Vein Reports context supports the Vein Signals setup.",
            data_quality="partial",
        )

    return _wrap(
        symbol=symbol,
        direction=direction,
        status="MIXED",
        recommendation="CAUTION",
        directional_bias=bias,
        confidence=0.55,
        hard_blocks=[],
        warnings=warnings,
        supporting=supporting,
        contradicting=clean_contradicting,
        summary="Vein Reports context is mixed; treat as soft confirmation only.",
        data_quality="partial",
    )


def _collect_supply_chain_evidence(
    supply_chain: dict[str, Any],
    supporting: list[str],
    contradicting: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(supply_chain, dict) or not supply_chain:
        return
    if supply_chain.get("has_graph_coverage") is False:
        warnings.append("Supply-chain context has no graph coverage for this symbol.")
        return
    chokepoints = supply_chain.get("chokepoints") or []
    if chokepoints:
        severity = str(supply_chain.get("maxChokepointSeverity") or supply_chain.get("severity") or "").upper()
        if severity in {"CRITICAL", "HIGH"}:
            contradicting.append("HARD:Supply-chain chokepoint severity elevated.")
        else:
            supporting.append("Supply-chain chokepoints available for contextual review.")


def _collect_intelligence_evidence(
    intelligence: dict[str, Any],
    supporting: list[str],
    contradicting: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(intelligence, dict) or not intelligence:
        return
    status = str(intelligence.get("status") or intelligence.get("retrievalStatus") or "").lower()
    if status in {"empty", "error"}:
        warnings.append("Intelligence brief unavailable or empty.")
        return
    bias = _normalize_bias_token(
        intelligence.get("directionalBias")
        or intelligence.get("sentimentBias")
        or intelligence.get("bias")
        or intelligence.get("overall_band")
    )
    if bias in {"BULLISH", "BEARISH", "MIXED"}:
        if bias == "MIXED":
            warnings.append("Intelligence brief sentiment is mixed.")
        else:
            supporting.append(f"Intelligence brief directional bias: {bias}.")
    event_risk = intelligence.get("eventRisk") or intelligence.get("event_risk")
    if event_risk:
        contradicting.append("HARD:Near-term event risk in intelligence brief.")
    summary = intelligence.get("summary") or intelligence.get("headline")
    if summary and bias not in {"BULLISH", "BEARISH", "MIXED"}:
        supporting.append("Intelligence brief present for contextual review.")


def _normalize_bias_token(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if any(token in text for token in ("BUY", "LONG", "BULL")):
        return "BULLISH"
    if any(token in text for token in ("SELL", "SHORT", "BEAR")):
        return "BEARISH"
    if any(token in text for token in ("HOLD", "NEUTRAL", "MIXED")):
        return "MIXED"
    return text


def _collect_cached_report_evidence(
    cached: dict[str, Any],
    raw_signal: str,
    supporting: list[str],
    contradicting: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(cached, dict) or not cached:
        return
    bias = str(cached.get("directionalBias") or cached.get("bias") or "").upper()
    if not bias:
        return
    if bias == "MIXED":
        warnings.append("Cached report bias is mixed.")
        return
    agrees = (
        (raw_signal == "ENTER_LONG" and bias in {"BULLISH", "POSITIVE", "LONG"})
        or (raw_signal == "ENTER_SHORT" and bias in {"BEARISH", "NEGATIVE", "SHORT"})
    )
    conflicts = (
        (raw_signal == "ENTER_LONG" and bias in {"BEARISH", "NEGATIVE", "SHORT"})
        or (raw_signal == "ENTER_SHORT" and bias in {"BULLISH", "POSITIVE", "LONG"})
    )
    if agrees:
        supporting.append(f"Cached report directional bias agrees ({bias}).")
    elif conflicts:
        contradicting.append(f"Cached report directional bias conflicts ({bias}).")


def _infer_bias(raw_signal: str, supporting: list[str], contradicting: list[str]) -> str:
    if contradicting and not supporting:
        # Opposite of signal when only contradictions
        if raw_signal == "ENTER_LONG":
            return "BEARISH"
        if raw_signal == "ENTER_SHORT":
            return "BULLISH"
        return "MIXED"
    if supporting and not contradicting:
        return _directional_bias(raw_signal)
    return "MIXED"


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
    data_quality: str,
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
        "dataQuality": data_quality,
        "contextSource": "report-validation-lite",
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
