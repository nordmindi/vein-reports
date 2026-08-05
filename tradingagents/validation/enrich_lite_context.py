"""Optional context enrichment for report-validation-lite.

Vein Signals stays unaware of Explorer/Aggregator. Vein Reports optionally
pulls sibling context (fail-open, short timeouts) before lite validation.
Caller-supplied context always wins over fetched context.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingagents.service.trace_logging import log_info, log_warning


def enrich_lite_payload(
    payload: dict[str, Any],
    *,
    jobs: dict[str, Any] | None = None,
    reports_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Return a copy of payload with optional report-side context filled in."""
    enriched = dict(payload)
    symbol = str(enriched.get("symbol") or "").strip().upper()
    provenance: dict[str, Any] = {
        "supplyChain": "caller" if _has_mapping(enriched.get("supplyChainContext") or enriched.get("supply_chain_context")) else "missing",
        "intelligence": "caller" if _has_mapping(enriched.get("intelligenceBrief") or enriched.get("intelligence_brief")) else "missing",
        "reportContext": "caller" if _has_mapping(enriched.get("reportContext") or enriched.get("report_context")) else "missing",
    }

    if not symbol:
        enriched["_liteEnrichment"] = provenance
        return enriched

    if provenance["supplyChain"] == "missing" and _lite_explorer_enabled():
        bundle = _fetch_explorer_context(symbol)
        if bundle is not None:
            enriched["supplyChainContext"] = bundle
            provenance["supplyChain"] = "explorer"

    if provenance["intelligence"] == "missing" and _lite_aggregator_enabled():
        brief = _fetch_intelligence_brief(symbol)
        if brief is not None:
            enriched["intelligenceBrief"] = brief
            provenance["intelligence"] = "aggregator"

    if provenance["reportContext"] == "missing":
        cached = _latest_report_context(symbol, jobs=jobs, reports_dir=reports_dir)
        if cached is not None:
            enriched["reportContext"] = cached
            provenance["reportContext"] = "local_cache"

    enriched["_liteEnrichment"] = provenance
    log_info(
        "report_validation_lite_enrichment",
        symbol=symbol,
        supplyChain=provenance["supplyChain"],
        intelligence=provenance["intelligence"],
        reportContext=provenance["reportContext"],
    )
    return enriched


def briefs_to_intelligence_brief(
    bundle: dict[str, Any] | None,
    briefs: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize Aggregator bundle/briefs into lite intelligenceBrief shape."""
    if not isinstance(bundle, dict) and not isinstance(briefs, dict):
        return None

    briefs = briefs if isinstance(briefs, dict) else {}
    sentiment = briefs.get("sentiment") if isinstance(briefs.get("sentiment"), dict) else {}
    news = briefs.get("news") if isinstance(briefs.get("news"), dict) else {}
    retrieval = {}
    if isinstance(bundle, dict):
        retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}

    band = (
        sentiment.get("overall_band")
        or news.get("headline_sentiment_band")
        or sentiment.get("bias")
        or ""
    )
    bias = _normalize_bias(band)
    status = str(retrieval.get("status") or ("ok" if briefs else "empty")).lower()
    event_risk = bool(
        news.get("event_risk")
        or sentiment.get("event_risk")
        or news.get("eventRisk")
        or _earnings_like(news)
    )
    summary = (
        sentiment.get("headline")
        or sentiment.get("narrative")
        or news.get("headline")
        or ""
    )
    return {
        "status": status,
        "retrievalStatus": status,
        "directionalBias": bias,
        "sentimentBias": bias,
        "summary": summary,
        "eventRisk": event_risk,
        "source": "vein-aggregator",
    }


def _lite_explorer_enabled() -> bool:
    override = os.getenv("TRADINGAGENTS_LITE_EXPLORER_ENABLED", "").strip().lower()
    if override in {"0", "false", "no", "off"}:
        return False
    if override in {"1", "true", "yes", "on"}:
        return True
    from tradingagents.integrations.vein_explorer_client import is_vein_pull_enabled

    return is_vein_pull_enabled()


def _lite_aggregator_enabled() -> bool:
    override = os.getenv("TRADINGAGENTS_LITE_AGGREGATOR_ENABLED", "").strip().lower()
    if override in {"0", "false", "no", "off"}:
        return False
    if override in {"1", "true", "yes", "on"}:
        return True
    from tradingagents.integrations.vein_aggregator_client import is_vein_aggregator_enabled

    return is_vein_aggregator_enabled()


def _fetch_explorer_context(symbol: str) -> dict[str, Any] | None:
    from tradingagents.integrations.vein_explorer_client import fetch_supply_chain_context

    timeout = _float_env("TRADINGAGENTS_LITE_EXPLORER_TIMEOUT_SEC", 8.0)
    try:
        return fetch_supply_chain_context(symbol, timeout_seconds=timeout)
    except Exception as exc:  # noqa: BLE001 — fail-open
        log_warning(
            "lite_explorer_enrich_failed",
            symbol=symbol,
            error=str(exc),
            errorType=exc.__class__.__name__,
        )
        return None


def _fetch_intelligence_brief(symbol: str) -> dict[str, Any] | None:
    from tradingagents.integrations.vein_aggregator_client import fetch_intelligence_bundle

    timeout = _float_env("TRADINGAGENTS_LITE_AGGREGATOR_TIMEOUT_SEC", 8.0)
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        bundle, briefs = fetch_intelligence_bundle(
            symbol,
            end_date=end_date,
            lookback_days=int(_float_env("TRADINGAGENTS_LITE_AGGREGATOR_LOOKBACK_DAYS", 7)),
            timeout_seconds=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open
        log_warning(
            "lite_aggregator_enrich_failed",
            symbol=symbol,
            error=str(exc),
            errorType=exc.__class__.__name__,
        )
        return None
    return briefs_to_intelligence_brief(bundle, briefs)


def _latest_report_context(
    symbol: str,
    *,
    jobs: dict[str, Any] | None,
    reports_dir: Path | str | None,
) -> dict[str, Any] | None:
    ticker = symbol.strip().upper()
    candidates: list[tuple[datetime, dict[str, Any]]] = []

    for record in (jobs or {}).values():
        try:
            request = getattr(record, "request", None)
            result = getattr(record, "result", None)
            status = str(getattr(getattr(record, "status", None), "value", getattr(record, "status", ""))).lower()
            if status != "completed" or result is None or request is None:
                continue
            if str(getattr(request, "ticker", "") or "").strip().upper() != ticker:
                continue
            completed_at = getattr(record, "completed_at", None) or getattr(record, "created_at", None)
            if not isinstance(completed_at, datetime):
                completed_at = datetime.min.replace(tzinfo=timezone.utc)
            bias = _bias_from_decision(getattr(result, "decision", None))
            report_dir = getattr(result, "report_dir", None)
            if bias == "MIXED" and report_dir:
                bias = _bias_from_dashboard(Path(report_dir)) or bias
            if bias == "MIXED":
                continue
            candidates.append(
                (
                    completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc),
                    {
                        "directionalBias": bias,
                        "bias": bias,
                        "source": "completed_job",
                        "jobId": getattr(record, "job_id", None),
                    },
                )
            )
        except Exception:  # noqa: BLE001
            continue

    if reports_dir:
        for item in _scan_report_dirs(Path(reports_dir), ticker):
            candidates.append(item)

    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][1]


def _scan_report_dirs(root: Path, ticker: str) -> list[tuple[datetime, dict[str, Any]]]:
    if not root.exists():
        return []
    found: list[tuple[datetime, dict[str, Any]]] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return []
    for child in children:
        if not child.is_dir():
            continue
        dashboard = child / "dashboard.json"
        if not dashboard.exists():
            continue
        try:
            payload = json.loads(dashboard.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        symbol = str(payload.get("symbol") or payload.get("ticker") or "").upper()
        if symbol and symbol != ticker:
            continue
        # Prefer explicit ticker match; if missing, skip scan ambiguity
        if not symbol:
            continue
        bias = _normalize_bias(payload.get("recommendation") or payload.get("decision") or "")
        if bias == "MIXED":
            continue
        mtime = datetime.fromtimestamp(dashboard.stat().st_mtime, tz=timezone.utc)
        found.append(
            (
                mtime,
                {
                    "directionalBias": bias,
                    "bias": bias,
                    "source": "dashboard_cache",
                    "path": str(dashboard),
                },
            )
        )
    return found


def _bias_from_dashboard(report_dir: Path) -> str | None:
    path = report_dir / "dashboard.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    bias = _normalize_bias(payload.get("recommendation") or payload.get("decision") or "")
    return bias if bias != "MIXED" else None


def _bias_from_decision(decision: Any) -> str:
    if decision is None:
        return "MIXED"
    if isinstance(decision, dict):
        return _normalize_bias(
            decision.get("recommendation")
            or decision.get("action")
            or decision.get("decision")
            or ""
        )
    return _normalize_bias(decision)


def _normalize_bias(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return "MIXED"
    if any(token in text for token in ("BUY", "LONG", "BULL")):
        return "BULLISH"
    if any(token in text for token in ("SELL", "SHORT", "BEAR")):
        return "BEARISH"
    if any(token in text for token in ("HOLD", "NEUTRAL", "MIXED", "INSUFFICIENT")):
        return "MIXED"
    return "MIXED"


def _earnings_like(news: dict[str, Any]) -> bool:
    text = " ".join(
        str(news.get(key) or "")
        for key in ("headline", "summary", "narrative", "headline_sentiment_band")
    ).lower()
    return "earnings" in text and any(token in text for token in ("today", "tomorrow", "this week", "imminent"))


def _has_mapping(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
