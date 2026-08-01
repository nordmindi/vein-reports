import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup
from tradingagents.integrations.intelligence_target import IntelligenceTarget
from tradingagents.service.runner import ReportRequest, validate_report_request


@pytest.mark.unit
class TestReportRequestValidation:
    def test_accepts_supply_chain_analyst(self):
        request = ReportRequest(
            ticker="TSLA",
            analysis_date="2026-06-30",
            selected_analysts=("market", "supply_chain"),
            context_bundle={
                "version": "vein-context-v1",
                "primary_symbol": "TSLA",
                "has_graph_coverage": True,
                "anchor_elements": [],
                "downstream_products": [],
                "related_companies": [],
                "chokepoints": [],
                "peer_tickers_for_news": [],
            },
        )

        validate_report_request(request)

    def test_rejects_vein_symbol_mismatch(self):
        request = ReportRequest(
            ticker="TSLA",
            analysis_date="2026-06-30",
            selected_analysts=("supply_chain",),
            context_bundle={
                "version": "vein-context-v1",
                "primary_symbol": "NVDA",
                "has_graph_coverage": True,
                "anchor_elements": [],
                "downstream_products": [],
                "related_companies": [],
                "chokepoints": [],
                "peer_tickers_for_news": [],
            },
        )

        with pytest.raises(ValueError, match="primary_symbol must match ticker"):
            validate_report_request(request)

    def test_accepts_sector_target_without_ticker(self):
        request = ReportRequest(
            analysis_date="2026-06-30",
            intelligence_target=IntelligenceTarget(type="sector", value="mining"),
            selected_analysts=("market", "news"),
        )

        validate_report_request(request)

    def test_rejects_ticker_and_target_together(self):
        request = ReportRequest(
            ticker="TSLA",
            analysis_date="2026-06-30",
            intelligence_target=IntelligenceTarget(type="sector", value="mining"),
            selected_analysts=("market",),
        )

        with pytest.raises(ValueError, match="not both"):
            validate_report_request(request)


@pytest.mark.unit
class TestSupplyChainGraphSetup:
    def test_supply_chain_graph_builds_without_tool_node(self):
        setup = GraphSetup(
            quick_thinking_llm=None,
            deep_thinking_llm=None,
            tool_nodes={},
            conditional_logic=ConditionalLogic(),
        )

        workflow = setup.setup_graph(["supply_chain"])

        assert workflow is not None
