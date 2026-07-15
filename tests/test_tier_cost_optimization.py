import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup
from tradingagents.service.tier_profiles import TIER_PROFILES, apply_tier_profile


class _Message:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls


@pytest.mark.unit
class TestTierProfiles:
    def test_free_tier_enables_lite_pipeline(self):
        config = apply_tier_profile({}, "free")
        assert config["pipeline_mode"] == "lite"
        assert config["max_tool_rounds_per_analyst"] == 2
        assert config["news_article_limit"] == 8

    def test_pro_tier_uses_full_pipeline(self):
        config = apply_tier_profile({}, "pro")
        assert config["pipeline_mode"] == "full"
        assert config["use_deep_research_manager"] is False
        assert config["use_deep_portfolio_manager"] is True

    def test_unknown_tier_falls_back_to_pro(self):
        config = apply_tier_profile({}, "enterprise")
        assert config["pipeline_mode"] == TIER_PROFILES["pro"]["pipeline_mode"]


@pytest.mark.unit
class TestToolLoopCaps:
    def test_caps_market_tool_rounds(self):
        logic = ConditionalLogic(max_tool_rounds_per_analyst=2)
        state = {
            "messages": [
                _Message(tool_calls=[{"name": "get_stock_data"}]),
            ]
        }
        assert logic.should_continue_market(state) == "tools_market"

        state["messages"].append(_Message(tool_calls=[{"name": "get_indicators"}]))
        assert logic.should_continue_market(state) == "Msg Clear Market"

    def test_unlimited_when_cap_none(self):
        logic = ConditionalLogic(max_tool_rounds_per_analyst=None)
        state = {"messages": [_Message(tool_calls=[{"name": "x"}]) for _ in range(5)]}
        assert logic.should_continue_market(state) == "tools_market"


@pytest.mark.unit
class TestLiteGraphSetup:
    def test_lite_pipeline_builds_without_debate_nodes_wired(self):
        setup = GraphSetup(
            quick_thinking_llm=None,
            deep_thinking_llm=None,
            tool_nodes={},
            conditional_logic=ConditionalLogic(),
            pipeline_mode="lite",
        )
        workflow = setup.setup_graph(["market"])
        assert workflow is not None
