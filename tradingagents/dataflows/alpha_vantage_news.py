import json

from .alpha_vantage_common import _make_api_request, format_datetime_for_api
from .errors import NoMarketDataError


def _ensure_news_payload(payload, *, symbol: str, detail: str):
    """Raise NoMarketDataError when Alpha Vantage returns an empty news feed."""
    if payload is None:
        raise NoMarketDataError(symbol, symbol, detail)

    parsed = payload
    if isinstance(payload, str):
        text = payload.strip()
        if not text or text in {"{}", "[]", "null"}:
            raise NoMarketDataError(symbol, symbol, detail)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return payload

    if isinstance(parsed, dict):
        feed = parsed.get("feed")
        if isinstance(feed, list) and len(feed) == 0:
            raise NoMarketDataError(symbol, symbol, detail)
        if "feed" not in parsed:
            raise NoMarketDataError(symbol, symbol, detail)
    return payload


def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """

    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
    }

    payload = _make_api_request("NEWS_SENTIMENT", params)
    return _ensure_news_payload(
        payload,
        symbol=ticker,
        detail=f"no Alpha Vantage news between {start_date} and {end_date}",
    )

def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> dict[str, str] | str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back (default 7).
        limit: Maximum number of articles (default 50).

    Returns:
        Dictionary containing global news sentiment data or JSON string.
    """
    from datetime import datetime, timedelta

    # Calculate start date
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(curr_date),
        "limit": str(limit),
    }

    payload = _make_api_request("NEWS_SENTIMENT", params)
    return _ensure_news_payload(
        payload,
        symbol="GLOBAL",
        detail=f"no Alpha Vantage global news between {start_date} and {curr_date}",
    )


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """

    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)
