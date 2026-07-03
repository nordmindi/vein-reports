from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    build_vein_news_context,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])
        vein_news_context = build_vein_news_context(state.get("vein_context_bundle"))

        tools = [
            get_news,
        ]

        system_message = (
            "You are a public-sentiment researcher for company-specific news and social discussion during the requested window. Maximize factual accuracy and traceability. Prefer a short and incomplete report that is fully supported over a comprehensive report containing unsupported claims. Use the get_news(query, start_date, end_date) tool to search for company-specific news and public discussion. Distinguish observed sentiment, verified events, and interpretation. Do not convert article attention, watch-list popularity, or search volume into institutional buying unless fund-flow or ownership evidence exists. Report missing or conflicting evidence instead of filling gaps. Do not issue BUY, HOLD, or SELL."
            + """ Append a concise Markdown table at the end of the report to organize supported key points."""
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
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}{vein_news_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(vein_news_context=vein_news_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
