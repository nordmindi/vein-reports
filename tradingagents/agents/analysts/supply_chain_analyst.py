from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


def create_supply_chain_analyst(llm=None):
    def supply_chain_analyst_node(state):
        report = render_supply_chain_report(
            state.get("company_of_interest", ""),
            state.get("vein_context_bundle"),
        )
        return {
            "messages": [AIMessage(content=report)],
            "supply_chain_report": report,
        }

    return supply_chain_analyst_node


def render_supply_chain_report(ticker: str, context_bundle: Any) -> str:
    bundle = _as_dict(context_bundle)
    if not bundle:
        return _no_coverage_report(ticker, "No Vein context bundle was supplied.")

    version = str(bundle.get("version") or "unknown")
    generated_at = str(bundle.get("generated_at") or "not recorded")
    primary_symbol = str(bundle.get("primary_symbol") or ticker or "Unknown").upper()

    if bundle.get("has_graph_coverage") is not True:
        return _no_coverage_report(
            primary_symbol,
            "Vein Graph has no supply-chain coverage for this symbol yet.",
            version=version,
            generated_at=generated_at,
        )

    company = _as_dict(bundle.get("company")) or {}
    company_name = company.get("name") or primary_symbol
    anchor_elements = _clean_items(bundle.get("anchor_elements"), ("name",))
    downstream_products = _clean_items(
        bundle.get("downstream_products"),
        ("name", "category", "hops", "is_chokepoint"),
    )
    related_companies = _clean_items(
        bundle.get("related_companies"),
        ("symbol", "name", "via", "via_chokepoint"),
    )
    chokepoints = _clean_items(
        bundle.get("chokepoints"),
        ("name", "category", "hops", "via"),
    )
    peer_tickers = [
        str(item).strip().upper()
        for item in _as_list(bundle.get("peer_tickers_for_news"))[:24]
        if str(item).strip()
    ]
    watchlist_notes = str(bundle.get("watchlist_notes") or "").strip()

    sections = [
        "### Supply Chain & Chokepoint Analysis",
        (
            f"Per Vein Graph structural analysis for {company_name} "
            f"({primary_symbol}) as of {generated_at}. "
            "This is supply-chain structure, not a transaction recommendation."
        ),
        f"- Source: Vein Graph ({version}).",
        "- Evidence status: model-assisted structural context; not filing-verified by this report unless separately stated.",
        "- Decision use: background risk and context only.",
        "",
        "#### Anchor Products",
        _bullet_list([item["name"] for item in anchor_elements], "No anchor products were supplied."),
        "",
        "#### Downstream Dependencies",
        _downstream_table(downstream_products),
        "",
        "#### Chokepoints",
        _chokepoint_table(chokepoints),
        "",
        "#### Related Listed Companies",
        _related_company_table(related_companies),
        "",
        "#### News Widening Candidates",
        _bullet_list(peer_tickers, "No peer tickers were supplied for news widening."),
    ]

    if watchlist_notes:
        sections.extend(
            [
                "",
                "#### User Research Focus",
                f"- {watchlist_notes}",
                "- This note is user-authored framing, not verified market evidence.",
            ]
        )

    return "\n".join(sections)


def _no_coverage_report(
    ticker: str,
    reason: str,
    *,
    version: str = "not supplied",
    generated_at: str = "not recorded",
) -> str:
    symbol = str(ticker or "Unknown").upper()
    return "\n".join(
        [
            "### Supply Chain & Chokepoint Analysis",
            f"- Symbol: {symbol}",
            f"- Source: Vein Graph ({version}).",
            f"- Generated At: {generated_at}",
            f"- Status: {reason}",
            "- Publication note: No supply-chain claims are made from missing Vein coverage.",
        ]
    )


def _downstream_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No downstream dependencies were supplied."
    rows = []
    for item in sorted(items, key=lambda value: (value.get("hops") is None, value.get("hops") or 0, value.get("name") or "")):
        rows.append(
            (
                item.get("name") or "Not recorded",
                item.get("category") or "Not recorded",
                str(item.get("hops") if item.get("hops") is not None else "Not recorded"),
                "Yes" if item.get("is_chokepoint") is True else "No",
            )
        )
    return _markdown_table(("Dependency", "Category", "Hops", "Chokepoint"), rows)


def _chokepoint_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No chokepoints were supplied."
    rows = []
    for item in items[:20]:
        rows.append(
            (
                item.get("name") or "Not recorded",
                item.get("category") or "Not recorded",
                str(item.get("hops") if item.get("hops") is not None else "Not recorded"),
                item.get("via") or "Not recorded",
            )
        )
    return _markdown_table(("Chokepoint", "Category", "Hops", "Via"), rows)


def _related_company_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No related listed companies were supplied."
    rows = []
    for item in items[:24]:
        rows.append(
            (
                item.get("symbol") or "Not recorded",
                item.get("name") or "Not recorded",
                item.get("via") or "Not recorded",
                "Yes" if item.get("via_chokepoint") is True else "No",
            )
        )
    return _markdown_table(("Ticker", "Company", "Connection", "Via Chokepoint"), rows)


def _bullet_list(items: list[str], empty_text: str) -> str:
    cleaned = [item for item in items if item]
    if not cleaned:
        return empty_text
    return "\n".join(f"- {item}" for item in cleaned)


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_table_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _table_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "/").strip() or "Not recorded"


def _clean_items(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    cleaned = []
    for item in _as_list(value):
        item_dict = _as_dict(item)
        if not item_dict:
            continue
        cleaned.append({key: item_dict.get(key) for key in keys})
    return cleaned


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_dict(value: Any) -> dict | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None
