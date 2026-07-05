from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

import pandas as pd
from pydantic import BaseModel

FreshnessStatus = Literal["fresh", "stale", "blocked", "no_data", "unsupported"]


class MarketDataFreshness(BaseModel):
    ticker: str
    requested_as_of: date
    provider: str = "yfinance"
    market_data_session: date | None = None
    sessions_stale: int | None = None
    freshness_status: FreshnessStatus
    max_completed_sessions_old: int
    recommendation_allowed: bool
    warnings: list[str] = []


def check_market_data_freshness(
    symbol: str,
    requested_date: str | date,
    *,
    max_completed_sessions_old: int = 2,
) -> MarketDataFreshness:
    """Return a best-effort freshness record for daily market data."""
    requested = _parse_date(requested_date)
    try:
        import yfinance as yf

        start = requested - timedelta(days=30)
        end = requested + timedelta(days=1)
        history = yf.Ticker(symbol.upper()).history(start=start.isoformat(), end=end.isoformat())
    except Exception as exc:
        return MarketDataFreshness(
            ticker=symbol.upper(),
            requested_as_of=requested,
            freshness_status="unsupported",
            max_completed_sessions_old=max_completed_sessions_old,
            recommendation_allowed=False,
            warnings=[f"Market-data freshness lookup failed: {exc}"],
        )

    if history is None or history.empty:
        return MarketDataFreshness(
            ticker=symbol.upper(),
            requested_as_of=requested,
            freshness_status="no_data",
            max_completed_sessions_old=max_completed_sessions_old,
            recommendation_allowed=False,
            warnings=["No OHLCV data was returned for the requested date window."],
        )

    session = _last_session_on_or_before(history, requested)
    if session is None:
        return MarketDataFreshness(
            ticker=symbol.upper(),
            requested_as_of=requested,
            freshness_status="no_data",
            max_completed_sessions_old=max_completed_sessions_old,
            recommendation_allowed=False,
            warnings=["No market-data session was available on or before the requested date."],
        )

    sessions_stale = _business_sessions_between(session, requested)
    if sessions_stale > max_completed_sessions_old:
        status: FreshnessStatus = "blocked"
    elif sessions_stale > 0:
        status = "stale"
    else:
        status = "fresh"

    return MarketDataFreshness(
        ticker=symbol.upper(),
        requested_as_of=requested,
        market_data_session=session,
        sessions_stale=sessions_stale,
        freshness_status=status,
        max_completed_sessions_old=max_completed_sessions_old,
        recommendation_allowed=status == "fresh",
        warnings=[] if status == "fresh" else [
            f"Market data are {sessions_stale} completed sessions old."
        ],
    )


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _last_session_on_or_before(history: pd.DataFrame, requested: date) -> date | None:
    index = pd.to_datetime(history.index, errors="coerce")
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    sessions = sorted({ts.date() for ts in index if pd.notna(ts) and ts.date() <= requested})
    return sessions[-1] if sessions else None


def _business_sessions_between(last_session: date, requested: date) -> int:
    if last_session >= requested:
        return 0
    start = last_session + timedelta(days=1)
    return len(pd.bdate_range(start=start, end=requested))
