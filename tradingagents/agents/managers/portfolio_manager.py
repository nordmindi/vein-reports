"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.validation.evidence import usable_historical_lessons


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_context = state["trader_investment_plan"]

        validated_lessons = usable_historical_lessons(state)
        lessons_line = (
            "- Validated historical lessons available for this decision:\n"
            f"{_format_validated_lessons(validated_lessons)}\n"
            if validated_lessons
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry
- **Insufficient Evidence**: Do not recommend a transaction because core evidence is stale, missing, unauditable, or internally unsupported

**Context:**
- Research Manager's evidence synthesis: **{research_plan}**
- Trader's execution context: **{trader_context}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Use only canonical evidence available in the current analyst reports, research synthesis, trader context, and risk debate.
Treat research and trader text as non-final context, not as transaction authority.
Prefer Insufficient Evidence over any directional rating when market data are stale, current fundamentals are missing, metrics are not present in the active report, historical lessons are not auditable, or a price target lacks a documented valuation method.
Do not infer institutional buying, accumulation, distribution, or divergence unless those claims are explicitly validated in the current evidence.
Use neutral, professional, falsifiable language. Avoid hype, insults, tribal framing, inevitability wording, pressure-to-act phrasing, or phrases such as "smart money", "catastrophic", "extremely compelling", "very compelling", "clash violently", "massive mistake", "gambling", and "screaming sell signal".
Ground every conclusion in specific verified evidence from the current run.{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node


def _format_validated_lessons(lessons) -> str:
    lines = []
    for lesson in lessons:
        lines.append(
            "- "
            f"{lesson.lesson_id} | {lesson.ticker} | {lesson.recommendation} | "
            f"net_return={lesson.net_return} | alpha={lesson.alpha} | "
            f"holding_period_sessions={lesson.holding_period_sessions} | "
            f"sources={','.join(lesson.source_ids)}"
        )
    return "\n".join(lines)
