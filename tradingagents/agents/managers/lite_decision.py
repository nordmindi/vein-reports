"""Single-call final decision for lite (free-tier) report pipelines."""

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

_ANALYST_REPORT_FIELDS = (
    ("market_report", "Market"),
    ("sentiment_report", "Sentiment"),
    ("news_report", "News"),
    ("fundamentals_report", "Fundamentals"),
    ("supply_chain_report", "Supply Chain"),
)


def create_lite_decision_agent(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Lite Decision")

    def lite_decision_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        sections: list[str] = []
        for field, label in _ANALYST_REPORT_FIELDS:
            text = str(state.get(field) or "").strip()
            if text:
                sections.append(f"### {label}\n{text}")

        analyst_section = "\n\n".join(sections) if sections else "(No analyst reports available)"

        prompt = f"""As a concise equity analyst, produce a final trading decision using only the analyst report(s) below.

{instrument_context}

---

{analyst_section}

---

**Rating Scale** (use exactly one):
- **Buy**, **Overweight**, **Hold**, **Underweight**, **Sell**, or **Insufficient Evidence**

Prefer Insufficient Evidence when core market data are stale, missing, or unauditable.
Use neutral, professional language.{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Lite Decision",
        )

        return {
            "investment_plan": final_trade_decision,
            "trader_investment_plan": "",
            "final_trade_decision": final_trade_decision,
        }

    return lite_decision_node
