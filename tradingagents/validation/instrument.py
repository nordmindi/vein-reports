from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

InstrumentStatus = Literal["resolved", "ambiguous", "unlisted", "unsupported", "not_found"]


class InstrumentRecord(BaseModel):
    instrument_id: str
    requested_query: str
    canonical_symbol: str
    exchange: str | None = None
    currency: str | None = None
    quote_type: str | None = None
    instrument_type: str = "other"
    listed: bool
    otc: bool = False
    share_class: str | None = None
    status: Literal["active", "inactive", "delisted", "unlisted", "unknown"] = "unknown"
    source: str = "yfinance"


class InstrumentResolution(BaseModel):
    requested_query: str
    status: InstrumentStatus
    selected_instrument_id: str | None = None
    candidates: list[InstrumentRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    user_confirmation_required: bool = False


def resolve_instrument(symbol: str) -> InstrumentResolution:
    """Best-effort instrument resolution for publication gating.

    This is not a full security master. It prevents the highest-risk failure
    modes first: free-form share-class queries, missing listings, and provider
    substitutions that do not match the requested ticker.
    """
    requested = symbol.strip().upper()
    if _looks_like_freeform_share_class(requested):
        return InstrumentResolution(
            requested_query=requested,
            status="ambiguous",
            warnings=[
                "Ticker appears to include a free-form share class. Use an exchange-qualified symbol."
            ],
            user_confirmation_required=True,
        )

    try:
        import yfinance as yf

        ticker = yf.Ticker(requested)
        info = getattr(ticker, "info", None) or {}
    except Exception as exc:
        return InstrumentResolution(
            requested_query=requested,
            status="unsupported",
            warnings=[f"Instrument metadata lookup failed: {exc}"],
            user_confirmation_required=False,
        )

    canonical_symbol = _first_nonempty(
        info.get("symbol"),
        info.get("underlyingSymbol"),
        info.get("shortName") if _is_symbol_like(info.get("shortName")) else None,
        requested,
    ).upper()
    exchange = _first_nonempty(info.get("exchange"), info.get("fullExchangeName"))
    currency = _first_nonempty(info.get("currency"), info.get("financialCurrency"))
    quote_type = info.get("quoteType")
    instrument_type = _map_quote_type(quote_type)
    otc = _is_otc(exchange, info)
    listed = bool(exchange) and not otc

    if _metadata_is_empty(info):
        return InstrumentResolution(
            requested_query=requested,
            status="not_found",
            warnings=["No instrument metadata was returned by the data provider."],
            user_confirmation_required=True,
        )

    record = InstrumentRecord(
        instrument_id=f"yf:{canonical_symbol}",
        requested_query=requested,
        canonical_symbol=canonical_symbol,
        exchange=exchange,
        currency=currency,
        quote_type=quote_type,
        instrument_type=instrument_type,
        listed=listed,
        otc=otc,
        share_class=_infer_share_class(requested),
        status="active" if exchange else "unknown",
    )

    warnings: list[str] = []
    user_confirmation_required = False
    status: InstrumentStatus = "resolved"

    if canonical_symbol != requested:
        warnings.append(
            f"Provider canonical symbol '{canonical_symbol}' differs from requested '{requested}'."
        )
        user_confirmation_required = True

    if not exchange:
        warnings.append("No exchange was returned for the instrument.")
        status = "unlisted"
        user_confirmation_required = True

    return InstrumentResolution(
        requested_query=requested,
        status=status,
        selected_instrument_id=record.instrument_id,
        candidates=[record],
        warnings=warnings,
        user_confirmation_required=user_confirmation_required,
    )


def _looks_like_freeform_share_class(symbol: str) -> bool:
    # Examples: "SAAB A", "BRK B". Exchange tickers should use the provider
    # syntax, e.g. "BRK-B" or an exchange suffix such as ".ST".
    return bool(re.fullmatch(r"[A-Z0-9]{1,8}\s+[A-Z]{1,3}", symbol))


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _is_symbol_like(value: Any) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[A-Z0-9.\-]{1,16}", value.upper()))


def _metadata_is_empty(info: dict[str, Any]) -> bool:
    if not info:
        return True
    meaningful_keys = {"symbol", "exchange", "quoteType", "currency", "shortName", "longName"}
    return not any(info.get(key) for key in meaningful_keys)


def _map_quote_type(quote_type: str | None) -> str:
    value = (quote_type or "").upper()
    return {
        "EQUITY": "ordinary_share",
        "ETF": "etf",
        "MUTUALFUND": "fund",
        "INDEX": "index",
        "CRYPTOCURRENCY": "crypto",
        "CURRENCY": "fx",
    }.get(value, "other")


def _is_otc(exchange: str | None, info: dict[str, Any]) -> bool:
    text = " ".join(
        str(part or "").upper()
        for part in (
            exchange,
            info.get("fullExchangeName"),
            info.get("market"),
        )
    )
    return any(marker in text for marker in ("OTC", "PNK", "PINK", "GREY"))


def _infer_share_class(symbol: str) -> str | None:
    if "-" in symbol:
        return symbol.rsplit("-", 1)[-1]
    return None
