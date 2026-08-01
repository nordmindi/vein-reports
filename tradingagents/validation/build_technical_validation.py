"""Build structured ``technical_validation`` metadata from OHLCV data."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.market_data_validator import _verified_rows
from tradingagents.validation.technical import (
    bollinger_squeeze_valid,
    detect_cross,
    macd_components_reconcile,
)


def build_technical_validation(
    symbol: str,
    curr_date: str,
    *,
    lookback_days: int = 252,
) -> dict[str, Any]:
    """Compute auditable technical metadata for publication validation."""
    df = _verified_rows(symbol, curr_date)
    if len(df) > lookback_days:
        df = df.tail(lookback_days).reset_index(drop=True)

    stock_df = wrap(df.copy())
    dates = [row["Date"].strftime("%Y-%m-%d") for _, row in df.iterrows()]

    for name in (
        "close_50_sma",
        "close_200_sma",
        "rsi",
        "boll",
        "boll_ub",
        "boll_lb",
        "macd",
        "macds",
        "macdh",
    ):
        with suppress(Exception):
            stock_df[name]

    metadata: dict[str, Any] = {
        "moving_average_cross": _latest_moving_average_cross(stock_df, dates),
        "macd": _latest_macd_metadata(stock_df),
        "bollinger_squeeze": _latest_bollinger_squeeze(stock_df),
        "volume_inference": _latest_volume_inference(df),
        "streak_calculations": _latest_streak_calculations(stock_df, dates),
    }
    return {key: value for key, value in metadata.items() if value}


def attach_technical_validation(final_state: dict, symbol: str, trade_date: str) -> None:
    """Populate ``final_state['technical_validation']`` when absent."""
    if final_state.get("technical_validation"):
        return
    try:
        final_state["technical_validation"] = build_technical_validation(
            symbol,
            trade_date,
        )
    except Exception:  # noqa: BLE001 — metadata is best-effort; validation will gate claims
        final_state["technical_validation"] = {}


def _latest_moving_average_cross(stock_df: pd.DataFrame, dates: list[str]) -> dict[str, Any]:
    sma50 = stock_df["close_50_sma"].tolist()
    sma200 = stock_df["close_200_sma"].tolist()
    latest = {"event": "no_new_cross", "event_date": None}

    for index in range(1, len(sma50)):
        if pd.isna(sma50[index - 1]) or pd.isna(sma200[index - 1]):
            continue
        if pd.isna(sma50[index]) or pd.isna(sma200[index]):
            continue
        cross = detect_cross(
            [float(sma50[index - 1]), float(sma50[index])],
            [float(sma200[index - 1]), float(sma200[index])],
            dates=[dates[index - 1], dates[index]],
        )
        if cross["event"] != "no_new_cross":
            latest = cross

    return latest


def _latest_macd_metadata(stock_df: pd.DataFrame) -> dict[str, Any] | None:
    row = stock_df.iloc[-1]
    required = ("macd", "macds", "macdh")
    if any(pd.isna(row.get(key)) for key in required):
        return None

    macd_line = float(row["macd"])
    signal_line = float(row["macds"])
    histogram = float(row["macdh"])
    tolerance = 1e-6
    if not macd_components_reconcile(
        macd_line,
        signal_line,
        histogram,
        tolerance=tolerance,
    ):
        return None

    return {
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
        "tolerance": tolerance,
    }


def _latest_bollinger_squeeze(stock_df: pd.DataFrame) -> dict[str, Any] | None:
    required = ("boll_ub", "boll", "boll_lb")
    if not all(name in stock_df.columns for name in required):
        return None

    widths: list[float] = []
    for _, row in stock_df.iterrows():
        upper, middle, lower = row["boll_ub"], row["boll"], row["boll_lb"]
        if pd.isna(upper) or pd.isna(middle) or pd.isna(lower) or middle == 0:
            continue
        widths.append((float(upper) - float(lower)) / float(middle))

    if not widths:
        return None

    latest = stock_df.iloc[-1]
    upper = float(latest["boll_ub"])
    middle = float(latest["boll"])
    lower = float(latest["boll_lb"])
    current_width = (upper - lower) / middle if middle else None
    if current_width is None:
        return None

    width_percentile = sum(1 for width in widths if width <= current_width) / len(widths)
    threshold = 0.15
    validated = bollinger_squeeze_valid(
        upper_band=upper,
        middle_band=middle,
        lower_band=lower,
        width_percentile=width_percentile,
        threshold=threshold,
    )
    return {
        "validated": validated,
        "upper_band": upper,
        "middle_band": middle,
        "lower_band": lower,
        "width_percentile": width_percentile,
        "threshold": threshold,
    }


def _latest_volume_inference(df: pd.DataFrame) -> dict[str, Any] | None:
    if "Volume" not in df.columns or df.empty:
        return None

    volumes = pd.to_numeric(df["Volume"], errors="coerce").dropna()
    if volumes.empty:
        return None

    window = min(20, len(volumes))
    recent = volumes.tail(window)
    latest_volume = float(recent.iloc[-1])
    average_volume = float(recent.mean())
    ratio = latest_volume / average_volume if average_volume else None

    close_change_pct = None
    if len(df) >= 2 and "Close" in df.columns:
        prev_close = float(df.iloc[-2]["Close"])
        latest_close = float(df.iloc[-1]["Close"])
        if prev_close:
            close_change_pct = (latest_close - prev_close) / prev_close * 100

    return {
        "validated": True,
        "latest_volume": latest_volume,
        "average_volume_20d": average_volume,
        "volume_ratio": ratio,
        "latest_close_change_pct": close_change_pct,
    }


def _latest_streak_calculations(
    stock_df: pd.DataFrame,
    dates: list[str],
) -> dict[str, Any] | None:
    if "rsi" not in stock_df.columns:
        return None

    oversold_threshold = 30.0
    streak = 0
    for index in range(len(stock_df) - 1, -1, -1):
        rsi = stock_df.iloc[index]["rsi"]
        if pd.isna(rsi) or float(rsi) >= oversold_threshold:
            break
        streak += 1

    losing_streak = 0
    if "close" in stock_df.columns and len(stock_df) >= 2:
        for index in range(len(stock_df) - 1, 0, -1):
            prev_close = stock_df.iloc[index - 1]["close"]
            curr_close = stock_df.iloc[index]["close"]
            if pd.isna(prev_close) or pd.isna(curr_close):
                break
            if float(curr_close) >= float(prev_close):
                break
            losing_streak += 1

    max_oversold_streak = 0
    current = 0
    for index in range(len(stock_df)):
        rsi = stock_df.iloc[index]["rsi"]
        if pd.isna(rsi) or float(rsi) >= oversold_threshold:
            current = 0
            continue
        current += 1
        max_oversold_streak = max(max_oversold_streak, current)

    return {
        "rsi_oversold_consecutive_sessions": streak,
        "rsi_oversold_max_sessions_lookback": max_oversold_streak,
        "losing_day_streak": losing_streak,
        "rsi_threshold": oversold_threshold,
        "as_of_date": dates[-1] if dates else None,
    }
