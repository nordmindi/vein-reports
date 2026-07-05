from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NewsRetrievalStatus = Literal[
    "NEWS_VENDOR_SUCCESS",
    "PEER_NEWS_FALLBACK_USED",
    "PEER_NEWS_FALLBACK_FAILED",
    "NEWS_VENDOR_COVERAGE_FAILURE",
    "PRIMARY_SOURCE_FALLBACK_USED",
    "PRIMARY_SOURCE_FALLBACK_FAILED",
    "PRIMARY_SOURCE_FALLBACK_NOT_ATTEMPTED",
]


class NewsRetrievalStatusRecord(BaseModel):
    ticker: str
    start_date: date
    end_date: date
    status: NewsRetrievalStatus
    vendor_results_count: int = 0
    peer_fallback_attempted: bool = False
    peer_results_count: int = 0
    peer_tickers_queried: list[str] = Field(default_factory=list)
    fallback_attempted: bool = False
    primary_results_count: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def check_news_retrieval(
    ticker: str,
    start_date: str | date,
    end_date: str | date,
    context_bundle: dict[str, Any] | None = None,
) -> NewsRetrievalStatusRecord:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    symbol = ticker.upper()
    warnings: list[str] = []

    vendor_results = _vendor_news(symbol, start, end, warnings)
    if vendor_results:
        return NewsRetrievalStatusRecord(
            ticker=symbol,
            start_date=start,
            end_date=end,
            status="NEWS_VENDOR_SUCCESS",
            vendor_results_count=len(vendor_results),
            results=vendor_results,
        )

    peer_tickers = _peer_tickers(context_bundle, symbol)
    peer_results = _peer_news(peer_tickers, start, end, warnings)
    if peer_results:
        return NewsRetrievalStatusRecord(
            ticker=symbol,
            start_date=start,
            end_date=end,
            status="PEER_NEWS_FALLBACK_USED",
            vendor_results_count=0,
            peer_fallback_attempted=True,
            peer_results_count=len(peer_results),
            peer_tickers_queried=peer_tickers,
            results=peer_results,
            warnings=warnings
            + [
                "Primary ticker news returned no usable results; supplemented with Vein supply-chain peer news."
            ],
        )

    fallback_results = _primary_source_fallback(symbol, start, end, warnings)
    status: NewsRetrievalStatus = (
        "PRIMARY_SOURCE_FALLBACK_USED"
        if fallback_results
        else "PRIMARY_SOURCE_FALLBACK_FAILED"
    )
    return NewsRetrievalStatusRecord(
        ticker=symbol,
        start_date=start,
        end_date=end,
        status=status,
        vendor_results_count=0,
        peer_fallback_attempted=bool(peer_tickers),
        peer_results_count=0,
        peer_tickers_queried=peer_tickers,
        fallback_attempted=True,
        primary_results_count=len(fallback_results),
        results=fallback_results,
        warnings=warnings,
    )


def _peer_news(
    peer_tickers: list[str],
    start: date,
    end: date,
    warnings: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for peer in peer_tickers:
        peer_results = _vendor_news(peer, start, end, warnings)
        for result in peer_results:
            annotated = dict(result)
            annotated["source_type"] = "vein_peer_news"
            annotated["peer_ticker"] = peer
            annotated["supplemental_for"] = "primary_ticker_news_vacuum"
            results.append(annotated)
    return results


def _peer_tickers(context_bundle: dict[str, Any] | None, primary_symbol: str) -> list[str]:
    if not isinstance(context_bundle, dict):
        return []
    if context_bundle.get("has_graph_coverage") is not True:
        return []
    raw = context_bundle.get("peer_tickers_for_news") or []
    if not isinstance(raw, list):
        return []
    peers = []
    seen = {primary_symbol.upper()}
    for value in raw:
        symbol = str(value).strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        peers.append(symbol)
        if len(peers) >= 24:
            break
    return peers


def _vendor_news(symbol: str, start: date, end: date, warnings: list[str]) -> list[dict[str, Any]]:
    try:
        import yfinance as yf

        stock = yf.Ticker(symbol)
        news = stock.get_news(count=20) or []
    except Exception as exc:
        warnings.append(f"Vendor news lookup failed: {exc}")
        return []

    results = []
    for article in news:
        parsed = _extract_yfinance_news(article)
        published = _coerce_date(parsed.get("published_at"))
        if published is not None and not (start <= published <= end):
            continue
        results.append(parsed)
    return results


def _primary_source_fallback(symbol: str, start: date, end: date, warnings: list[str]) -> list[dict[str, Any]]:
    try:
        import yfinance as yf

        stock = yf.Ticker(symbol)
        filings = getattr(stock, "sec_filings", None)
        if callable(filings):
            filings = filings()
    except Exception as exc:
        warnings.append(f"Primary-source fallback lookup failed: {exc}")
        return []

    if filings is None:
        return []

    if hasattr(filings, "to_dict"):
        raw_items = filings.to_dict("records")
    elif isinstance(filings, list):
        raw_items = filings
    else:
        raw_items = []

    results = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        filed_at = _coerce_date(
            item.get("date")
            or item.get("filingDate")
            or item.get("acceptedDate")
            or item.get("filed")
        )
        if filed_at is not None and not (start <= filed_at <= end):
            continue
        results.append(
            {
                "source_type": "SEC filing",
                "title": item.get("type") or item.get("form") or "SEC filing",
                "published_at": filed_at.isoformat() if filed_at else None,
                "url": item.get("edgarUrl") or item.get("url") or item.get("link"),
            }
        )
    return results


def _extract_yfinance_news(article: dict) -> dict[str, Any]:
    content = article.get("content") if isinstance(article.get("content"), dict) else article
    published = _coerce_date(content.get("pubDate") or content.get("providerPublishTime"))
    provider = content.get("provider")
    if isinstance(provider, dict):
        provider = provider.get("displayName")
    return {
        "source_type": "news_vendor",
        "title": content.get("title") or "Untitled news item",
        "publisher": provider or content.get("publisher"),
        "published_at": published.isoformat() if published else None,
        "url": _extract_url(content),
    }


def _extract_url(content: dict) -> str | None:
    for key in ("canonicalUrl", "clickThroughUrl"):
        value = content.get(key)
        if isinstance(value, dict) and value.get("url"):
            return value.get("url")
    return content.get("link")


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
    return None
