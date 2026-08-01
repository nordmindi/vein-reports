"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def _state():
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2026-01-15",
        "market_report": "Market observations show improving momentum with volume confirmation near recent lows.",
        "news_report": "NEWS",
        "investment_plan": "Research synthesis without an explicit rating.",
        "investment_debate_state": {"judge_decision": "RM PLAN"},
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"judge_decision": "PM DECISION"},
        "final_trade_decision": "**Rating**: Hold\n\n**Executive Summary**: Test summary.",
        "instrument_resolution": {
            "requested_query": "AAPL",
            "status": "resolved",
            "selected_instrument_id": "yf:AAPL",
            "candidates": [
                {
                    "instrument_id": "yf:AAPL",
                    "requested_query": "AAPL",
                    "canonical_symbol": "AAPL",
                    "exchange": "NMS",
                    "currency": "USD",
                    "quote_type": "EQUITY",
                    "instrument_type": "ordinary_share",
                    "listed": True,
                    "otc": False,
                    "share_class": None,
                    "status": "active",
                    "source": "yfinance",
                }
            ],
            "warnings": [],
            "user_confirmation_required": False,
        },
        "market_data_freshness": {
            "ticker": "AAPL",
            "requested_as_of": "2026-01-15",
            "provider": "yfinance",
            "market_data_session": "2026-01-15",
            "sessions_stale": 0,
            "freshness_status": "fresh",
            "max_completed_sessions_old": 2,
            "recommendation_allowed": True,
            "warnings": [],
        },
        "technical_validation": {},
    }


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert out.name == "complete_report.md"
    assert (tmp_path / "1_analysts" / "market.md").read_text().startswith("Market observations")
    assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
    assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
    assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
    decision = (tmp_path / "5_portfolio" / "decision.md").read_text()
    assert "Insufficient Evidence" in decision
    assert (tmp_path / "validation_report.json").exists()
    assert (tmp_path / "dashboard.json").exists()
    assert (tmp_path / "final_report.json").exists()
    complete = out.read_text()
    assert "Trading Analysis Report: AAPL" in complete
    assert "## Executive Summary" in complete
    assert "Executive Dashboard" not in complete
    assert "Insufficient evidence" in complete or "Insufficient Evidence" in complete
    assert "improving momentum" in complete
    assert "<tool_call>" not in complete


@pytest.mark.unit
def test_save_reports_explicit_path(tmp_path):
    # Unbound: with an explicit save_path, the method doesn't touch self/config.
    out = TradingAgentsGraph.save_reports(None, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    mock_self = SimpleNamespace(config={"results_dir": str(tmp_path)})
    out = TradingAgentsGraph.save_reports(mock_self, _state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")


@pytest.mark.unit
def test_write_report_tree_strips_tool_call_markup(tmp_path):
    bear_with_tool_call = (
        "Bear Analyst: I'll gather data.\n"
        "<tool_call>\n"
        '<tool name="ddg-search">\n'
        '<parameter name="query">Sumco Corporation</parameter>\n'
        "</tool>\n"
        "</tool_call>\n"
        "The silicon wafer cycle remains weak into 2026."
    )
    state = _state()
    state["investment_debate_state"] = {
        "bear_history": bear_with_tool_call,
        "judge_decision": "RM PLAN",
    }
    out = write_report_tree(state, "3436.T", tmp_path)
    bear_md = (tmp_path / "2_research" / "bear.md").read_text()
    complete = out.read_text()
    assert "<tool_call>" not in bear_md
    assert "<tool_call>" not in complete
    assert "silicon wafer cycle remains weak" in bear_md
