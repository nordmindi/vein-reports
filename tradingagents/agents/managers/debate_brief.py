"""Compress analyst reports before bull/bear and risk debate agents."""

from __future__ import annotations

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.debate_context import collect_analyst_reports_for_brief

_MAX_BRIEF_CHARS = 12_000


def create_debate_brief_agent(llm):
    def debate_brief_node(state) -> dict:
        combined = collect_analyst_reports_for_brief(state)
        if not combined.strip():
            return {"debate_brief": ""}

        instrument_context = get_instrument_context_from_state(state)
        prompt = f"""Compress the analyst reports below into a single debate brief for investment researchers.

{instrument_context}

Requirements:
- Max ~2000 words; preserve concrete numbers, dates, tickers, and named risks/catalysts
- Do not invent facts not present in the source reports
- Include supply-chain points when present
- Use clear sections: Market, Sentiment, News, Fundamentals, Supply Chain (omit empty sections)

Source reports:
{combined}
{get_language_instruction()}"""

        response = llm.invoke(prompt)
        brief = getattr(response, "content", response)
        if not isinstance(brief, str):
            brief = str(brief)
        if len(brief) > _MAX_BRIEF_CHARS:
            brief = brief[:_MAX_BRIEF_CHARS] + "\n...(truncated)"
        return {"debate_brief": brief.strip()}

    return debate_brief_node
