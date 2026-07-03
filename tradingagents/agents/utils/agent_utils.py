from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def build_vein_news_context(context_bundle: dict | None) -> str:
    if not isinstance(context_bundle, dict) or context_bundle.get("has_graph_coverage") is not True:
        return ""

    peers = [
        str(item).strip().upper()
        for item in (context_bundle.get("peer_tickers_for_news") or [])[:24]
        if str(item).strip()
    ]
    anchors = [
        str(item.get("name")).strip()
        for item in context_bundle.get("anchor_elements") or []
        if isinstance(item, dict) and item.get("name")
    ]
    downstream = [
        str(item.get("name")).strip()
        for item in context_bundle.get("downstream_products") or []
        if isinstance(item, dict) and item.get("name")
    ]

    parts = []
    if peers:
        parts.append(
            "If primary ticker news coverage is thin or empty, you may run supplemental news searches for these Vein supply-chain peer tickers: "
            + ", ".join(peers)
            + ". Treat peer results as supply-chain-adjacent context, not direct company news."
        )
    terms = anchors + downstream
    if terms:
        parts.append(
            "Relevant Vein supply-chain search terms: "
            + ", ".join(terms[:12])
            + ". Do not invent events from these terms."
        )
    if not parts:
        return ""
    return " Vein context: " + " ".join(parts)

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
