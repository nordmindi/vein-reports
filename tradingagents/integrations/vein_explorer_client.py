"""Optional pull client for Vein Explorer supply-chain context (HTTP only)."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def is_vein_pull_enabled() -> bool:
    raw = os.getenv("TRADINGAGENTS_VEIN_EXPLORER_ENABLED", "0").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(_base_url())


def _base_url() -> str:
    return os.getenv("TRADINGAGENTS_VEIN_EXPLORER_BASE_URL", "").strip().rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    key = (
        os.getenv("TRADINGAGENTS_VEIN_SERVICE_API_KEY", "").strip()
        or os.getenv("VEIN_SERVICE_API_KEY", "").strip()
    )
    if key:
        headers["x-vein-service-key"] = key
        headers["Authorization"] = f"Bearer {key}"
    return headers


def fetch_supply_chain_context(symbol: str, *, timeout_seconds: float = 20.0) -> dict[str, Any] | None:
    base = _base_url()
    if not base:
        return None

    ticker = symbol.strip().upper()
    try:
        response = requests.get(
            f"{base}/v1/integrations/supply-chain-context",
            params={"symbol": ticker},
            headers=_headers(),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Vein Explorer context fetch failed for %s: %s", ticker, exc)
        return None

    if not isinstance(body, dict):
        return None
    bundle = body.get("context_bundle") or body.get("supply_chain_context")
    if isinstance(bundle, dict):
        return bundle
    return None
