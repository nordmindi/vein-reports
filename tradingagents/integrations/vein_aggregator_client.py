"""HTTP client for Vein Aggregator intelligence feeds (no hard dependency)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import requests

from tradingagents.integrations.intelligence_target import IntelligenceTarget
from tradingagents.service.trace_logging import log_warning, trace_headers

INTELLIGENCE_VERSION = "vein-intelligence-v1"


def is_vein_aggregator_enabled() -> bool:
    raw = os.getenv("TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED", "0").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(_base_url())


def _base_url() -> str:
    return os.getenv("TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL", "").strip().rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json", **trace_headers()}
    key = os.getenv("TRADINGAGENTS_VEIN_AGGREGATOR_API_KEY", "").strip()
    if key:
        headers["X-API-Key"] = key
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _peer_symbols_from_context(context_bundle: dict[str, Any] | None) -> list[str]:
    if not isinstance(context_bundle, dict):
        return []
    if context_bundle.get("has_graph_coverage") is not True:
        return []
    raw = context_bundle.get("peer_tickers_for_news") or []
    if not isinstance(raw, list):
        return []
    return [str(v).strip().upper() for v in raw if str(v).strip()][:24]


def _search_terms_from_context(context_bundle: dict[str, Any] | None) -> list[str]:
    if not isinstance(context_bundle, dict):
        return []
    terms: list[str] = []
    for key in ("anchor_elements", "downstream_products"):
        for item in context_bundle.get(key) or []:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    terms.append(name)
    return terms[:12]


def _build_payload(
    *,
    symbol: str | None,
    target: IntelligenceTarget | None,
    end_date: str,
    context_bundle: dict[str, Any] | None,
    lookback_days: int,
) -> dict[str, Any]:
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=lookback_days)
    payload: dict[str, Any] = {
        "window": {
            "start": start_dt.strftime("%Y-%m-%d"),
            "end": end_date,
        },
        "peer_symbols": _peer_symbols_from_context(context_bundle),
        "include": ["news", "social", "macro", "prediction_markets"],
        "briefs": ["sentiment", "news"],
        "context_hints": {
            "search_terms": _search_terms_from_context(context_bundle),
            "vein_context_version": "vein-context-v1",
        },
    }
    if target is not None:
        payload["target"] = target.to_payload()
    elif symbol and symbol.strip():
        payload["symbol"] = symbol.strip().upper()
    else:
        raise ValueError("symbol or target is required for aggregator fetch")
    return payload


def fetch_intelligence_bundle(
    symbol: str | None = None,
    *,
    target: IntelligenceTarget | None = None,
    end_date: str,
    context_bundle: dict[str, Any] | None = None,
    lookback_days: int = 7,
    timeout_seconds: float = 90.0,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Pull vein-intelligence-v1 bundle and briefs from Vein Aggregator."""
    if not is_vein_aggregator_enabled():
        return None, None

    base = _base_url()
    if not base:
        return None, None

    subject = (symbol or (target.value if target else "") or "").strip().upper()
    try:
        payload = _build_payload(
            symbol=symbol,
            target=target,
            end_date=end_date,
            context_bundle=context_bundle,
            lookback_days=lookback_days,
        )
    except ValueError as exc:
        log_warning("vein_aggregator_invalid_request", subject=subject, error=str(exc))
        return None, None

    try:
        response = requests.post(
            f"{base}/v1/feeds/intelligence/briefs",
            json=payload,
            headers=_headers(),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        log_warning(
            "vein_aggregator_fetch_failed",
            subject=subject,
            error=str(exc),
            errorType=exc.__class__.__name__,
        )
        return None, None

    if not isinstance(body, dict):
        return None, None

    bundle = body.get("intelligence_bundle")
    if not isinstance(bundle, dict):
        bundle = body if body.get("version") == INTELLIGENCE_VERSION else None

    briefs_raw = body.get("briefs")
    briefs: dict[str, Any] | None = None
    if isinstance(briefs_raw, dict):
        briefs = briefs_raw

    if isinstance(bundle, dict) and bundle.get("version") != INTELLIGENCE_VERSION:
        log_warning(
            "vein_aggregator_unexpected_version",
            subject=subject,
            version=bundle.get("version"),
        )
    return bundle, briefs
