"""Tests for structured-output agents (Trader and Research Manager).

The Portfolio Manager has its own coverage in tests/test_memory_log.py
(which exercises the full memory-log → PM injection cycle).  This file
covers the parallel schemas, render functions, and graceful-fallback
behavior we added for the Trader and Research Manager so all three
decision-making agents share the same shape.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.analysts.supply_chain_analyst import render_supply_chain_report
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import (
    EvidenceBalance,
    ExecutionBias,
    ResearchPlan,
    TraderProposal,
    render_research_plan,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.agent_utils import build_vein_news_context


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderSupplyChainReport:
    def test_renders_vein_context_without_trade_guidance(self):
        report = render_supply_chain_report(
            "TSLA",
            {
                "version": "vein-context-v1",
                "primary_symbol": "TSLA",
                "has_graph_coverage": True,
                "company": {"name": "Tesla, Inc.", "symbol": "TSLA"},
                "anchor_elements": [{"name": "Electric vehicles"}],
                "downstream_products": [
                    {
                        "name": "EV battery packs",
                        "category": "energy",
                        "hops": 1,
                        "is_chokepoint": True,
                    }
                ],
                "related_companies": [
                    {
                        "symbol": "ALB",
                        "name": "Albemarle Corporation",
                        "via": "Lithium refining",
                        "via_chokepoint": True,
                    }
                ],
                "chokepoints": [
                    {"name": "Lithium refining", "category": None, "hops": 0, "via": "ALB"}
                ],
                "peer_tickers_for_news": ["ALB"],
                "watchlist_notes": "Watch margin and battery supply",
                "generated_at": "2026-06-30T18:00:00.000Z",
            },
        )

        assert "Per Vein Graph structural analysis" in report
        assert "Electric vehicles" in report
        assert "EV battery packs" in report
        assert "ALB" in report
        assert "user-authored framing" in report
        assert "**Recommendation**" not in report
        assert "BUY" not in report
        assert "SELL" not in report

    def test_no_coverage_does_not_invent_structural_claims(self):
        report = render_supply_chain_report(
            "OBSCURE",
            {
                "version": "vein-context-v1",
                "primary_symbol": "OBSCURE",
                "has_graph_coverage": False,
                "anchor_elements": [],
                "downstream_products": [],
                "related_companies": [],
                "chokepoints": [],
                "peer_tickers_for_news": [],
                "generated_at": "2026-06-30T18:00:00.000Z",
            },
        )

        assert "No supply-chain claims are made" in report
        assert "EV battery packs" not in report

    def test_vein_news_context_lists_peers_as_supplemental(self):
        context = build_vein_news_context(
            {
                "version": "vein-context-v1",
                "has_graph_coverage": True,
                "peer_tickers_for_news": ["ALB"],
                "anchor_elements": [{"name": "Electric vehicles"}],
                "downstream_products": [{"name": "EV battery packs"}],
            }
        )

        assert "ALB" in context
        assert "supply-chain-adjacent context" in context
        assert "Do not invent events" in context


@pytest.mark.unit
class TestRenderTraderProposal:
    def test_minimal_required_fields(self):
        p = TraderProposal(execution_bias=ExecutionBias.NEUTRAL, reasoning="Balanced setup; no edge.")
        md = render_trader_proposal(p)
        assert "**Execution Bias**: Neutral" in md
        assert "**Reasoning**: Balanced setup; no edge." in md
        assert "**Action**:" not in md
        assert "FINAL TRANSACTION PROPOSAL" not in md

    def test_optional_fields_included_when_present(self):
        p = TraderProposal(
            execution_bias=ExecutionBias.CONSTRUCTIVE,
            reasoning="Strong technicals + fundamentals.",
            entry_context="Watch for confirmation near support.",
            risk_context="Event risk remains elevated.",
            sizing_context="Sizing should account for volatility.",
        )
        md = render_trader_proposal(p)
        assert "**Execution Bias**: Constructive" in md
        assert "**Entry Context**: Watch for confirmation near support." in md
        assert "**Risk Context**: Event risk remains elevated." in md
        assert "**Sizing Context**: Sizing should account for volatility." in md
        assert "**Action**:" not in md
        assert "FINAL TRANSACTION PROPOSAL" not in md

    def test_optional_fields_omitted_when_absent(self):
        p = TraderProposal(execution_bias=ExecutionBias.DEFENSIVE, reasoning="Guidance risk.")
        md = render_trader_proposal(p)
        assert "Entry Context" not in md
        assert "Risk Context" not in md
        assert "Sizing Context" not in md
        assert "**Action**:" not in md
        assert "FINAL TRANSACTION PROPOSAL" not in md


@pytest.mark.unit
class TestRenderResearchPlan:
    def test_required_fields(self):
        p = ResearchPlan(
            evidence_balance=EvidenceBalance.BULL_CASE_STRONGER,
            bull_case_summary="Tailwinds intact.",
            bear_case_summary="Valuation risk remains.",
            uncertainties=["Await updated guidance."],
            decision_permitted=True,
            trader_context="Constructive context, but not a recommendation.",
        )
        md = render_research_plan(p)
        assert "**Evidence Balance**: Bull case stronger" in md
        assert "**Bull Case Summary**: Tailwinds intact." in md
        assert "**Bear Case Summary**: Valuation risk remains." in md
        assert "**Decision Permitted**: Yes" in md
        assert "- Await updated guidance." in md
        assert "**Recommendation**:" not in md

    def test_all_evidence_balance_values_render(self):
        for balance in EvidenceBalance:
            p = ResearchPlan(
                evidence_balance=balance,
                bull_case_summary="bull",
                bear_case_summary="bear",
                uncertainties=[],
                decision_permitted=True,
                trader_context="context",
            )
            md = render_research_plan(p)
            assert f"**Evidence Balance**: {balance.value}" in md


# ---------------------------------------------------------------------------
# Trader agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Evidence Balance**: Bull case stronger\n**Trader Context**: ...",
    }


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    """Build a MagicMock LLM whose with_structured_output binding captures the
    prompt and returns a real TraderProposal so render_trader_proposal works.
    """
    if proposal is None:
        proposal = TraderProposal(
            execution_bias=ExecutionBias.CONSTRUCTIVE,
            reasoning="Strong setup.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestTraderAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        proposal = TraderProposal(
            execution_bias=ExecutionBias.CONSTRUCTIVE,
            reasoning="AI capex cycle intact; institutional flows constructive.",
            entry_context="Watch for confirmation near support.",
            risk_context="Volatility remains elevated.",
            sizing_context="Sizing should reflect liquidity and event risk.",
        )
        llm = _structured_trader_llm(captured, proposal)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        plan = result["trader_investment_plan"]
        assert "**Execution Bias**: Constructive" in plan
        assert "**Entry Context**: Watch for confirmation near support." in plan
        assert "**Action**:" not in plan
        assert "FINAL TRANSACTION PROPOSAL" not in plan
        # The same rendered markdown is also added to messages for downstream agents.
        assert plan in result["messages"][0].content

    def test_prompt_includes_investment_plan(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm)
        trader(_make_trader_state())
        # The research synthesis is in the user message of the captured prompt.
        prompt = captured["prompt"]
        assert any("Research Synthesis" in m["content"] for m in prompt)

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = (
            "**Execution Bias**: Defensive\n\nGuidance risk affects execution context."
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        assert result["trader_investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Research Manager agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "Bull and bear arguments here.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _structured_rm_llm(captured: dict, plan: ResearchPlan | None = None):
    if plan is None:
        plan = ResearchPlan(
            evidence_balance=EvidenceBalance.BALANCED,
            bull_case_summary="Bull says...",
            bear_case_summary="Bear says...",
            uncertainties=["Need fresh data."],
            decision_permitted=True,
            trader_context="Neutral execution context.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or plan
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestResearchManagerAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        plan = ResearchPlan(
            evidence_balance=EvidenceBalance.BULL_CASE_STRONGER,
            bull_case_summary="AI tailwind intact.",
            bear_case_summary="Valuation risk remains.",
            uncertainties=[],
            decision_permitted=True,
            trader_context="Constructive context, no recommendation.",
        )
        llm = _structured_rm_llm(captured, plan)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        ip = result["investment_plan"]
        assert "**Evidence Balance**: Bull case stronger" in ip
        assert "**Bull Case Summary**: AI tailwind" in ip
        assert "**Trader Context**: Constructive context" in ip
        assert "**Recommendation**:" not in ip

    def test_prompt_uses_evidence_balance_scale(self):
        """The RM prompt must list evidence-balance values and avoid rating instructions."""
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        for balance in ("Bull case stronger", "Balanced", "Bear case stronger", "Insufficient evidence"):
            assert f"**{balance}**" in prompt, f"missing {balance} in prompt"
        assert "**Buy**" not in prompt
        assert "**Sell**" not in prompt

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = "**Evidence Balance**: Bear case stronger\n\n**Trader Context**: Defensive context."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        assert result["investment_plan"] == plain_response
