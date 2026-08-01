"""Unit tests for the Finnhub news vendor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError
from tradingagents.dataflows.finnhub_news import (
    FinnhubNotConfiguredError,
    get_global_news_finnhub,
    get_news_finnhub,
)


@pytest.mark.unit
def test_finnhub_requires_api_key(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(FinnhubNotConfiguredError):
        get_news_finnhub("TSLA", "2026-07-01", "2026-07-30")


@pytest.mark.unit
def test_finnhub_formats_company_news(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = [
        {
            "headline": "Tesla expands capacity",
            "source": "Yahoo",
            "summary": "Plant update.",
            "url": "https://example.com/a",
            "datetime": 1,
        }
    ]
    with patch("tradingagents.dataflows.finnhub_news._request", return_value=payload):
        out = get_news_finnhub("TSLA", "2026-07-01", "2026-07-30")
    assert "## TSLA News" in out
    assert "Tesla expands capacity" in out
    assert "source: Yahoo" in out


@pytest.mark.unit
def test_finnhub_empty_feed_raises(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    with (
        patch("tradingagents.dataflows.finnhub_news._request", return_value=[]),
        pytest.raises(NoMarketDataError),
    ):
        get_news_finnhub("TSLA", "2026-07-01", "2026-07-30")


@pytest.mark.unit
def test_finnhub_rejects_non_equity_symbols(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    with pytest.raises(NoMarketDataError):
        get_news_finnhub("XAUUSD", "2026-07-01", "2026-07-30")


@pytest.mark.unit
def test_finnhub_rate_limit_propagates(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    response = MagicMock()
    response.status_code = 429
    with (
        patch("tradingagents.dataflows.finnhub_news.requests.get", return_value=response),
        pytest.raises(VendorRateLimitError),
    ):
        get_news_finnhub("TSLA", "2026-07-01", "2026-07-30")


@pytest.mark.unit
def test_finnhub_global_news(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = [
        {
            "headline": "Fed holds rates",
            "source": "Reuters",
            "summary": "Policy unchanged.",
            "url": "https://example.com/b",
            "datetime": 4102444800,  # far future; still accepted as undated-bypass via window logic
        }
    ]
    # Use a realistic timestamp inside the lookback window relative to curr_date.
    from datetime import datetime

    ts = int(datetime(2026, 7, 28).timestamp())
    payload[0]["datetime"] = ts
    with patch("tradingagents.dataflows.finnhub_news._request", return_value=payload):
        out = get_global_news_finnhub("2026-07-30", look_back_days=7, limit=5)
    assert "Global Market News" in out
    assert "Fed holds rates" in out
