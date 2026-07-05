"""Research Manager: turns the bull/bear debate into non-final research synthesis."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a non-final research synthesis for the trader.

{instrument_context}

---

**Evidence Balance Scale** (use exactly one):
- **Bull case stronger**: Supported bull evidence is materially stronger than bear evidence
- **Balanced**: Supported evidence is mixed or roughly balanced
- **Bear case stronger**: Supported bear evidence is materially stronger than bull evidence
- **Insufficient evidence**: The debate lacks enough verified evidence for later decision review

Do not issue Buy, Sell, Hold, Overweight, Underweight, or any other investment recommendation.
Do not instruct the trader to execute a transaction. Summarize evidence, uncertainty, and non-final execution context only.
Use neutral, professional, falsifiable language. Avoid hype, insults, tribal framing, inevitability wording, pressure-to-act phrasing, or phrases such as "smart money", "catastrophic", "extremely compelling", "very compelling", "clash violently", "massive mistake", "gambling", and "screaming sell signal".

---

**Debate History:**
{history}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
