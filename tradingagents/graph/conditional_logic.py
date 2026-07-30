# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


def _count_tool_call_rounds(messages) -> int:
    count = 0
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            count += 1
    return count


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(
        self,
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_tool_rounds_per_analyst: int | None = None,
    ):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.max_tool_rounds_per_analyst = max_tool_rounds_per_analyst

    def _should_continue_with_tool_cap(
        self,
        state: AgentState,
        tools_label: str,
        clear_label: str,
    ) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            if (
                self.max_tool_rounds_per_analyst is not None
                and _count_tool_call_rounds(messages) >= self.max_tool_rounds_per_analyst
            ):
                return clear_label
            return tools_label
        return clear_label

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        return self._should_continue_with_tool_cap(state, "tools_market", "Msg Clear Market")

    def should_continue_social(self, state: AgentState):
        """Determine if sentiment-analyst tool round should continue."""
        return self._should_continue_with_tool_cap(state, "tools_social", "Msg Clear Sentiment")

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        return self._should_continue_with_tool_cap(state, "tools_news", "Msg Clear News")

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        return self._should_continue_with_tool_cap(
            state,
            "tools_fundamentals",
            "Msg Clear Fundamentals",
        )

    def should_continue_supply_chain(self, state: AgentState):
        """Supply-chain analyst has no tool loop; always proceed to clear."""
        return "Msg Clear Supply Chain"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
