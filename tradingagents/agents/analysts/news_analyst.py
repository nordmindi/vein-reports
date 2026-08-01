from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_vein_news_context,
    get_global_news,
    get_instrument_context_from_state,
    get_language_instruction,
    get_macro_indicators,
    get_news,
    get_non_authoritative_analyst_instruction,
    get_prediction_markets,
)
from tradingagents.agents.utils.analyst_invocation import invoke_analyst_with_tools
from tradingagents.integrations.intelligence_bundle_format import (
    format_news_analyst_context,
    has_intelligence_bundle,
    section_status,
)


def create_news_analyst(llm, max_tool_rounds: int | None = None):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)
        vein_news_context = build_vein_news_context(state.get("vein_context_bundle"))
        aggregator_context = ""
        if has_intelligence_bundle(state):
            bundle = state["vein_intelligence_bundle"]
            if section_status(bundle, "news") != "empty":
                aggregator_context = (
                    "\n\n<start_of_vein_aggregator_intelligence>\n"
                    + format_news_analyst_context(
                        bundle,
                        ticker,
                        briefs=state.get("vein_intelligence_briefs"),
                    )
                    + "\n<end_of_vein_aggregator_intelligence>\n"
                )

        tools = [
            get_news,
            get_global_news,
            get_macro_indicators,
            get_prediction_markets,
        ]

        system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends "
            f"over the past week for {ticker}. Write a comprehensive report of "
            f"{asset_label}-specific and macroeconomic developments relevant to trading. "
            + (
                "Vein Aggregator has pre-fetched news, macro, and prediction-market "
                "context in this prompt — synthesize it first; use tools only for gaps. "
                if aggregator_context
                else (
                    "Use the available tools with these exact signatures: "
                    f"get_news(ticker, start_date, end_date) for {asset_label}-specific news "
                    f'(pass ticker="{ticker}"), '
                    "get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news, "
                    "get_macro_indicators(indicator, curr_date, look_back_days) to ground macro "
                    "commentary in FRED data (e.g. 'cpi', 'core_pce', 'unemployment', "
                    "'fed_funds_rate', '10y_treasury', 'yield_curve'), and "
                    "get_prediction_markets(topic, limit) for live market-implied probabilities "
                    "(e.g. 'Fed rate cut', 'recession 2026', geopolitical or sector events). "
                    "Always call get_news at least once before writing the final report. "
                )
            )
            + "Provide specific insights with supporting evidence."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_non_authoritative_analyst_instruction("news brief")
            + vein_news_context
            + aggregator_context
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        return invoke_analyst_with_tools(
            llm=llm,
            prompt=prompt,
            tools=tools,
            messages=state["messages"],
            max_tool_rounds=max_tool_rounds,
            report_key="news_report",
        )

    return news_analyst_node
