"""Acceptance tests for curated report composition."""

import pytest

from tradingagents.report_composition import (
    ReportMode,
    build_final_report,
    compose_section_summary,
    determine_report_mode,
    is_agent_process_paragraph,
    render_final_report_markdown,
    sanitize_for_publication,
    scan_blocked_report_text,
    strip_agent_process_phrases,
)
from tradingagents.validation import ValidationResult, build_dashboard_model


def _state(**overrides):
    base = {
        "company_of_interest": "KTOS",
        "trade_date": "2026-06-26",
        "market_report": (
            "Now I have all data needed. Let me compile the comprehensive analysis.\n\n"
            "Price recovered above short-term levels with improving RSI."
        ),
        "sentiment_report": "Defense-sector sentiment remains constructive.",
        "news_report": "Contract wins support the medium-term narrative.",
        "fundamentals_report": "Revenue growth improved while free cash flow stayed negative.",
        "final_trade_decision": (
            "**Recommendation**: Watchlist\n\n"
            "**Synthesis**: Technical bounce is interesting but not yet actionable.\n\n"
            "**Investment Thesis**: Mixed evidence warrants patience."
        ),
        "instrument_resolution": {
            "selected_instrument_id": "yf:KTOS",
            "candidates": [{"source": "yfinance", "currency": "USD"}],
        },
        "market_data_freshness": {
            "provider": "yfinance",
            "market_data_session": "2026-06-26",
        },
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_executive_summary_replaces_dashboard_in_markdown():
    state = _state()
    validation = ValidationResult(status="research_only")
    dashboard = build_dashboard_model(state, validation)
    report = build_final_report(state, "KTOS", validation, dashboard)
    md = render_final_report_markdown(report)
    assert "## Executive Summary" in md
    assert "Executive Dashboard" not in md


@pytest.mark.unit
def test_blocked_report_has_no_transaction_language():
    state = _state(
        final_trade_decision=(
            "**Recommendation**: Insufficient evidence\n\n"
            "**Synthesis**: Validation blocked publication."
        ),
        risk_debate_state={
            "judge_decision": "**Recommendation**: Insufficient evidence",
        },
    )
    validation = ValidationResult(
        status="blocked",
        issues=[
            {
                "code": "RESEARCH_ONLY_ACTION_CONFLICT",
                "severity": "blocking",
                "message": "Conflicting transaction guidance detected.",
            }
        ],
    )
    dashboard = build_dashboard_model(state, validation)
    report = build_final_report(state, "KTOS", validation, dashboard)
    violations = scan_blocked_report_text(render_final_report_markdown(report))
    assert violations == []


@pytest.mark.unit
def test_raw_agent_phrases_removed_from_composed_sections():
    raw = (
        "Now I have all data needed. Let me compile the comprehensive analysis.\n\n"
        "Price recovered above short-term levels."
    )
    summary = compose_section_summary(raw, section_key="market_summary")
    rendered = render_final_report_markdown(
        build_final_report(
            _state(market_report=raw),
            "KTOS",
            ValidationResult(status="research_only"),
            build_dashboard_model(_state(), ValidationResult(status="research_only")),
        )
    )
    assert "now i have all data needed" not in summary.lower()
    assert "now i have all data needed" not in rendered.lower()


@pytest.mark.unit
def test_determine_report_mode_defaults_to_compact():
    assert determine_report_mode("verified") == ReportMode.COMPACT
    assert determine_report_mode("blocked") == ReportMode.BLOCKED
    assert determine_report_mode("verified", user_requested_full_report=True) == ReportMode.FULL


@pytest.mark.unit
def test_portfolio_manager_synthesis_uses_allowed_recommendations():
    state = _state()
    validation = ValidationResult(status="research_only")
    report = build_final_report(state, "KTOS", validation, build_dashboard_model(state, validation))
    assert report.portfolio_synthesis.recommendation in {
        "NO_CURRENT_TRANSACTION",
        "WATCHLIST",
        "TRADE_CANDIDATE",
        "RESEARCH_ONLY",
        "INSUFFICIENT_EVIDENCE",
    }


@pytest.mark.unit
def test_sanitize_strips_agent_process_phrases():
    text = "Now I have all the data needed. Let me compile the comprehensive report."
    assert strip_agent_process_phrases(text) == ""
    assert sanitize_for_publication(text) == ""


@pytest.mark.unit
def test_sanitize_strips_fundamental_analysis_preamble():
    text = ". Let me compile a comprehensive fundamental analysis report."
    assert strip_agent_process_phrases(text) == ""
    assert is_agent_process_paragraph(text) is True


@pytest.mark.unit
def test_first_substantial_paragraph_skips_agent_preamble():
    from tradingagents.report_composition.composer import _first_substantial_paragraph

    raw = (
        ". Let me compile a comprehensive fundamental analysis report.\n\n"
        "Revenue plateaued then declined from $97.69B in FY2023 to $94.83B in FY2025."
    )
    paragraph = _first_substantial_paragraph(raw)
    assert "let me compile" not in paragraph.lower()
    assert "Revenue plateaued" in paragraph
