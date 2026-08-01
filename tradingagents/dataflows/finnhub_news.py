"""Finnhub news vendor (company-news + market news).

Uses ``FINNHUB_API_KEY``. Company news covers North American equities; market
news provides general macro/financial headlines for ``get_global_news``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import requests

from .config import get_config
from .errors import NoMarketDataError, VendorNotConfiguredError, VendorRateLimitError
from .symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)

API_BASE_URL = "https://finnhub.io/api/v1"
REQUEST_TIMEOUT = 30


class FinnhubNotConfiguredError(VendorNotConfiguredError):
    """Raised when Finnhub is selected but no API key is configured."""


def get_api_key() -> str:
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise FinnhubNotConfiguredError(
            "FINNHUB_API_KEY environment variable is not set. "
            "Get a free key at https://finnhub.io/register."
        )
    return api_key


def _finnhub_equity_symbol(ticker: str) -> str:
    """Map user ticker to a Finnhub company-news symbol when possible."""
    canonical = normalize_symbol(ticker)
    if any(marker in canonical for marker in ("=", "^")) or (
        "-" in canonical and canonical.split("-")[-1] in {"USD", "USDT", "USDC"}
    ):
        raise NoMarketDataError(
            ticker,
            canonical,
            "Finnhub company-news covers equities only",
        )
    return canonical


def _request(path: str, params: dict) -> list | dict:
    api_params = dict(params)
    api_params["token"] = get_api_key()
    response = requests.get(
        f"{API_BASE_URL}{path}",
        params=api_params,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 429:
        raise VendorRateLimitError("Finnhub API rate limit exceeded")
    if response.status_code in {401, 403}:
        raise FinnhubNotConfiguredError(
            f"Finnhub rejected the API key (HTTP {response.status_code})."
        )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise VendorRateLimitError(str(payload["error"]))
    return payload


def _format_articles(articles: list[dict], *, limit: int) -> str:
    blocks: list[str] = []
    for article in articles[:limit]:
        title = str(article.get("headline") or article.get("title") or "").strip()
        if not title:
            continue
        source = str(article.get("source") or "Unknown").strip() or "Unknown"
        summary = str(article.get("summary") or "").strip()
        link = str(article.get("url") or "").strip()
        block = f"### {title} (source: {source})"
        if summary:
            block += f"\n{summary}"
        if link:
            block += f"\nLink: {link}"
        blocks.append(block)
    return "\n\n".join(blocks)


def get_news_finnhub(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve company news for a ticker from Finnhub."""
    symbol = _finnhub_equity_symbol(ticker)
    article_limit = get_config()["news_article_limit"]
    payload = _request(
        "/company-news",
        {"symbol": symbol, "from": start_date, "to": end_date},
    )
    if not isinstance(payload, list) or not payload:
        raise NoMarketDataError(
            ticker,
            symbol,
            f"no Finnhub company news between {start_date} and {end_date}",
        )

    body = _format_articles(payload, limit=article_limit)
    if not body:
        raise NoMarketDataError(
            ticker,
            symbol,
            f"no usable Finnhub headlines between {start_date} and {end_date}",
        )

    resolved = "" if symbol == ticker else f" (resolved to {symbol})"
    return f"## {ticker}{resolved} News, from {start_date} to {end_date}:\n\n{body}"


def get_global_news_finnhub(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve general market news from Finnhub."""
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    payload = _request("/news", {"category": "general"})
    if not isinstance(payload, list) or not payload:
        raise NoMarketDataError(
            "GLOBAL",
            "GLOBAL",
            f"no Finnhub market news near {curr_date}",
        )

    windowed: list[dict] = []
    for article in payload:
        ts = article.get("datetime")
        if ts is None:
            windowed.append(article)
            continue
        try:
            pub_dt = datetime.fromtimestamp(int(ts))
        except (TypeError, ValueError, OSError):
            windowed.append(article)
            continue
        if start_dt <= pub_dt <= curr_dt + timedelta(days=1):
            windowed.append(article)

    body = _format_articles(windowed or payload, limit=limit)
    if not body:
        raise NoMarketDataError(
            "GLOBAL",
            "GLOBAL",
            f"no usable Finnhub market headlines between {start_date} and {curr_date}",
        )
    return f"## Global Market News, from {start_date} to {curr_date}:\n\n{body}"
