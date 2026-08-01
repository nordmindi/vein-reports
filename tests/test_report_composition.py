"""Acceptance tests for curated report composition."""

import pytest

from tradingagents.report_composition import (
    ReportMode,
    build_final_report,
    compose_section_summary,
    determine_report_mode,
    is_agent_process_paragraph,
    redact_forbidden_transaction_language,
    render_final_report_markdown,
    sanitize_for_publication,
    scan_blocked_report_text,
    soften_rhetorical_language,
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
    assert determine_report_mode("research_only", user_requested_full_report=True) == ReportMode.FULL


@pytest.mark.unit
def test_research_only_includes_news_signal_and_risk_sections():
    state = _state(
        golden_trend_signal={
            "symbol": "KTOS",
            "rawSignal": "HOLD",
            "finalSignal": "NO_SIGNAL",
            "tradeAllowed": False,
            "confidenceScore": 0,
            "confidenceGrade": "F",
        },
        risk_debate_state={
            "aggressive_history": "Aggressive: upside skew remains if contracts accelerate.",
            "conservative_history": "Conservative: valuation still discounts execution risk.",
            "neutral_history": "Neutral: wait for confirmation before adding exposure.",
        },
    )
    validation = ValidationResult(status="research_only")
    report = build_final_report(state, "KTOS", validation, build_dashboard_model(state, validation))
    md = render_final_report_markdown(report)
    assert "## News and Sentiment Summary" in md
    assert "## Key Risks" in md
    assert "Vein Signals Validation" in md
    assert report.report_mode == ReportMode.COMPACT


@pytest.mark.unit
def test_full_report_mode_includes_appendix():
    state = _state(
        investment_debate_state={
            "bull_history": "Bull: growth remains intact.",
            "bear_history": "Bear: margins may compress.",
            "judge_decision": "Manager: mixed evidence.",
        }
    )
    validation = ValidationResult(status="research_only")
    report = build_final_report(
        state,
        "KTOS",
        validation,
        build_dashboard_model(state, validation),
        user_requested_full_report=True,
    )
    md = render_final_report_markdown(report)
    assert report.report_mode == ReportMode.FULL
    assert "## Appendix" in md
    assert "### Research Debate" in md


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
def test_sanitize_strips_market_analyst_preamble():
    text = (
        "I now have all the data needed to compile a comprehensive market "
        "structure report for NVDA. Let me analyze the findings."
    )
    assert strip_agent_process_phrases(text) == ""
    assert is_agent_process_paragraph(text) is True


@pytest.mark.unit
def test_first_substantial_paragraph_uses_analyst_executive_summary():
    from tradingagents.report_composition.composer import _first_substantial_paragraph

    raw = (
        "I now have all the data needed to compile a comprehensive market "
        "structure report for NVDA. Let me analyze the findings.\n\n"
        "---\n\n"
        "# NVDA — Market Structure Brief\n\n"
        "## Executive Summary\n\n"
        "NVDA has exhibited a pronounced short-to-medium term downtrend over "
        "the past two months, declining from approximately $224 in early June "
        "to $195 by late July."
    )
    paragraph = _first_substantial_paragraph(raw)
    assert "let me analyze" not in paragraph.lower()
    assert "i now have all the data" not in paragraph.lower()
    assert "pronounced short-to-medium term downtrend" in paragraph


@pytest.mark.unit
def test_signal_only_block_yields_research_only_status():
    from tradingagents.validation import validate_final_state

    state = _state(
        golden_trend_signal={
            "finalSignal": "NO_SIGNAL",
            "blocksTradePublication": True,
        },
        final_trade_decision="**Recommendation**: Research only\n\n**Synthesis**: Mixed evidence.",
        instrument_resolution={
            "status": "resolved",
            "selected_instrument_id": "yf:KTOS",
            "candidates": [{"source": "yfinance", "currency": "USD"}],
        },
        market_data_freshness={
            "freshness_status": "fresh",
            "recommendation_allowed": True,
            "sessions_stale": 0,
            "max_completed_sessions_old": 2,
        },
    )
    result = validate_final_state(state)
    assert result.status == "research_only"
    assert any(issue.code == "SIGNAL_SERVICE_BLOCKS_TRADE" for issue in result.blocking_issues)


@pytest.mark.unit
def test_blocked_nvda_style_report_uses_real_thesis():
    from tradingagents.report_composition.composer import build_final_report
    from tradingagents.validation import ValidationResult

    market = (
        "I now have all the data needed to compile a comprehensive market "
        "structure report for NVDA. Let me analyze the findings.\n\n"
        "## Executive Summary\n\n"
        "NVDA has exhibited a pronounced short-to-medium term downtrend over "
        "the past two months."
    )
    state = _state(market_report=market)
    validation = ValidationResult(
        status="blocked",
        issues=[
            {
                "code": "SIGNAL_SERVICE_BLOCKS_TRADE",
                "severity": "blocking",
                "location": "golden_trend_signal",
                "message": "Vein Signals blocked execution (NO_SIGNAL).",
            }
        ],
    )
    report = build_final_report(
        state, "NVDA", validation, build_dashboard_model(state, validation)
    )
    assert "let me analyze" not in report.executive_summary.lower()
    assert "i now have all the data" not in report.executive_summary.lower()
    assert "short-to-medium term downtrend" in report.executive_summary


@pytest.mark.unit
def test_section_headers_are_stripped_from_thesis():
    from tradingagents.report_composition.composer import _extract_thesis
    from tradingagents.report_composition.sanitizer import is_section_header_only

    assert is_section_header_only("## Portfolio Manager Synthesis: NVDA (NMS)") is True
    thesis = _extract_thesis(
        "## Portfolio Manager Synthesis: NVDA (NMS)\n\n"
        "NVDA remains in a corrective phase with mixed fundamental and technical evidence."
    )
    assert "portfolio manager synthesis" not in thesis.lower()
    assert "corrective phase" in thesis.lower()


@pytest.mark.unit
def test_executive_summary_omits_duplicate_headers_and_signal_block():
    state = _state(
        final_trade_decision=(
            "## Portfolio Manager Synthesis: NVDA (NMS)\n\n"
            "Mixed evidence keeps the setup on watchlist only."
        ),
        golden_trend_signal={
            "symbol": "NVDA",
            "rawSignal": "HOLD",
            "finalSignal": "NO_SIGNAL",
            "tradeAllowed": False,
            "confidenceScore": 0,
            "confidenceGrade": "F",
        },
    )
    validation = ValidationResult(status="research_only")
    report = build_final_report(state, "NVDA", validation, build_dashboard_model(state, validation))
    md = render_final_report_markdown(report)
    assert md.count("## Portfolio Manager Synthesis: NVDA") == 0
    assert md.count("## Vein Signals Validation") == 1
    assert "**Signal Service Result:**" not in md
    assert "Mixed evidence keeps the setup on watchlist only" in md
    text = "TSLA saw a catastrophic decline that looks inevitable after a screaming sell signal."
    softened = soften_rhetorical_language(text)
    assert "catastrophic" not in softened.lower()
    assert "inevitable" not in softened.lower()
    assert "screaming sell signal" not in softened.lower()
    assert "steep" in softened.lower()
    assert "likely" in softened.lower()


@pytest.mark.unit
def test_redact_transaction_terms_use_word_boundaries():
    text = "Selling pressure rose after FINAL TRANSACTION PROPOSAL: **SELL**."
    redacted = redact_forbidden_transaction_language(text)
    assert "FINAL TRANSACTION PROPOSAL" not in redacted
    assert "**SELL**" not in redacted
    # Ordinary prose must not become "[redacted]ing"
    assert "Selling" in redacted
    assert "[redacted]ing" not in redacted


@pytest.mark.unit
def test_composed_report_softens_rhetoric_in_executive_summary():
    state = _state(
        market_report=(
            "TSLA has experienced a catastrophic decline over the past month. "
            "A further drop looks inevitable without a catalyst."
        )
    )
    validation = ValidationResult(status="blocked")
    report = build_final_report(
        state, "TSLA", validation, build_dashboard_model(state, validation)
    )
    md = render_final_report_markdown(report)
    assert "catastrophic" not in md.lower()
    assert "inevitable" not in md.lower()
    assert "steep" in md.lower() or "likely" in md.lower()


@pytest.mark.unit
def test_blocking_reasons_are_deduplicated_and_short():
    from tradingagents.report_composition.composer import collect_publication_blocking_reasons
    from tradingagents.validation import ValidationIssue, ValidationResult

    validation = ValidationResult(
        status="blocked",
        issues=[
            ValidationIssue(
                code="MOVING_AVERAGE_CROSS_UNPROVEN",
                severity="blocking",
                location="market_report",
                message="Death cross claim lacks a dated code-detected crossover event.",
            ),
            ValidationIssue(
                code="MOVING_AVERAGE_CROSS_UNPROVEN",
                severity="blocking",
                location="market_report",
                message="Death cross claim lacks a dated code-detected crossover event.",
            ),
            ValidationIssue(
                code="UNSUPPORTED_VOLUME_INFERENCE",
                severity="blocking",
                location="market_report",
                message="Volume-based ownership-flow inference lacks structured validation.",
            ),
            ValidationIssue(
                code="UNSUPPORTED_VOLUME_INFERENCE",
                severity="blocking",
                location="bull_history",
                message="Volume-based ownership-flow inference lacks structured validation.",
            ),
            ValidationIssue(
                code="RHETORICAL_LANGUAGE",
                severity="blocking",
                location="final_trade_decision",
                message="Report output contains prohibited rhetorical or non-neutral language: 'catastrophic'.",
            ),
            ValidationIssue(
                code="RHETORICAL_LANGUAGE",
                severity="blocking",
                location="bull_history",
                message="Report output contains prohibited rhetorical or non-neutral language: 'catastrophic'.",
            ),
            ValidationIssue(
                code="UNSUPPORTED_STREAK_CLAIM",
                severity="blocking",
                location="claims",
                message=(
                    "Rejected downstream claim claim:e3917ad98cab3cc1: ## Portfolio Manager "
                    "Synthesis: TSLA Research Recommendation ### Summary of Analyst Debate "
                    + ("word " * 40)
                ),
            ),
        ],
    )
    reasons = collect_publication_blocking_reasons(validation)
    assert len(reasons) == 4
    assert reasons.count(
        "Death cross claim lacks a dated code-detected crossover event"
    ) == 1
    assert reasons.count(
        "Volume-based ownership-flow inference lacks structured validation"
    ) == 1
    assert "catastrophic" not in " ".join(reasons).lower()
    assert "severe" not in " ".join(reasons).lower()
    assert any("streak claims" in r.lower() for r in reasons)
    assert not any("Rejected downstream claim" in r for r in reasons)

    state = _state()
    report = build_final_report(
        state, "TSLA", validation, build_dashboard_model(state, validation)
    )
    md = render_final_report_markdown(report)
    # One Data Quality section; no duplicated Blocking Reasons dump.
    assert md.count("Death cross claim lacks a dated code-detected crossover event") == 1
    assert md.count("## Blocking Reasons") == 0
