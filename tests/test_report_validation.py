import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    render_pm_decision,
)
from tradingagents.reporting import write_report_tree
from tradingagents.validation import (
    ValidationResult,
    bearish_divergence,
    bollinger_squeeze_valid,
    build_dashboard_model,
    build_decision_evidence_bundle,
    bullish_divergence,
    check_market_data_freshness,
    check_news_retrieval,
    detect_cross,
    lesson_is_usable,
    macd_components_reconcile,
    rejected_claims,
    resolve_instrument,
    usable_historical_lessons,
    validate_final_state,
    verified_claims,
)


def _state(**overrides):
    base = {
        "company_of_interest": "NVDA",
        "trade_date": "2026-06-26",
        "market_report": "Market observations only.",
        "sentiment_report": "Sentiment observations only.",
        "news_report": "News observations only.",
        "fundamentals_report": "Fundamental observations only.",
        "investment_plan": "Research synthesis without an explicit rating.",
        "trader_investment_plan": "Trading synthesis without an explicit action.",
        "final_trade_decision": "**Rating**: Hold\n\n**Executive Summary**: Balanced.",
        "instrument_resolution": {
            "requested_query": "NVDA",
            "status": "resolved",
            "selected_instrument_id": "yf:NVDA",
            "candidates": [
                {
                    "instrument_id": "yf:NVDA",
                    "requested_query": "NVDA",
                    "canonical_symbol": "NVDA",
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
            "ticker": "NVDA",
            "requested_as_of": "2026-06-26",
            "provider": "yfinance",
            "market_data_session": "2026-06-26",
            "sessions_stale": 0,
            "freshness_status": "fresh",
            "max_completed_sessions_old": 2,
            "recommendation_allowed": True,
            "warnings": [],
        },
        "technical_validation": {},
    }
    base.update(overrides)
    return base


def _valid_lesson(**overrides):
    lesson = {
        "lesson_id": "LESSON-NVDA-20260501",
        "ticker": "NVDA",
        "original_run_id": "run-nvda-20260501",
        "original_decision_timestamp": "2026-05-01T14:30:00",
        "recommendation": "Hold",
        "entry_timestamp": "2026-05-01T14:30:00",
        "entry_price": "100.00",
        "exit_timestamp": "2026-05-08T20:00:00",
        "exit_price": "103.00",
        "benchmark_symbol": "SPY",
        "benchmark_entry": "500.00",
        "benchmark_exit": "505.00",
        "gross_return": "0.0300",
        "net_return": "0.0280",
        "benchmark_return": "0.0100",
        "alpha": "0.0180",
        "holding_period_sessions": 5,
        "transaction_cost_assumption_bps": "5",
        "slippage_assumption_bps": "5",
        "pattern_features": {"setup": "balanced"},
        "outcome_known_after_decision": True,
        "out_of_sample": True,
        "duplicate_group_id": None,
        "source_ids": ["memory:run-nvda-20260501"],
        "validation_status": "validated",
    }
    lesson.update(overrides)
    return lesson


@pytest.mark.unit
class TestReportValidation:
    def test_clean_legacy_state_is_research_only_not_verified(self):
        result = validate_final_state(
            _state(),
            expected_analysts=("market", "social", "news", "fundamentals"),
        )
        assert result.status == "research_only"
        assert result.status_label == "RESEARCH_OUTPUT"
        assert result.issues == []

    def test_missing_required_agent_blocks(self):
        result = validate_final_state(
            _state(news_report=""),
            expected_analysts=("market", "social", "news", "fundamentals"),
        )
        assert result.status == "blocked"
        assert result.has_blocking_issues
        assert result.blocking_issues[0].code == "FAILED_REQUIRED_AGENT"
        assert result.blocking_issues[0].location == "news_report"

    def test_supply_chain_required_agent_blocks_when_missing(self):
        result = validate_final_state(
            _state(supply_chain_report=""),
            expected_analysts=("market", "supply_chain"),
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "FAILED_REQUIRED_AGENT"
            and issue.location == "supply_chain_report"
            for issue in result.blocking_issues
        )

    def test_specialist_recommendation_blocks(self):
        result = validate_final_state(
            _state(market_report="**Recommendation**: Buy\nTrend is favorable."),
            expected_analysts=("market",),
        )
        assert result.status == "blocked"
        assert [issue.code for issue in result.blocking_issues] == [
            "UNAUTHORIZED_RECOMMENDATION"
        ]

    def test_supply_chain_recommendation_blocks(self):
        result = validate_final_state(
            _state(supply_chain_report="**Recommendation**: Buy because chokepoints matter."),
            expected_analysts=("supply_chain",),
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "UNAUTHORIZED_RECOMMENDATION"
            and issue.location == "supply_chain_report"
            for issue in result.blocking_issues
        )

    def test_vein_no_coverage_blocks_structural_claims(self):
        result = validate_final_state(
            _state(
                vein_context_bundle={
                    "version": "vein-context-v1",
                    "primary_symbol": "NVDA",
                    "has_graph_coverage": False,
                },
                supply_chain_report="Vein shows semiconductor packaging chokepoints.",
            )
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "VEIN_SUPPLY_CHAIN_CLAIM_WITHOUT_COVERAGE"
            for issue in result.blocking_issues
        )

    def test_vein_primary_symbol_mismatch_blocks(self):
        result = validate_final_state(
            _state(
                vein_context_bundle={
                    "version": "vein-context-v1",
                    "primary_symbol": "TSLA",
                    "has_graph_coverage": True,
                },
                supply_chain_report="Per Vein Graph structural analysis for TSLA.",
            )
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "VEIN_CONTEXT_SYMBOL_MISMATCH"
            for issue in result.blocking_issues
        )

    def test_multiple_decision_recommendations_warn_by_default(self):
        result = validate_final_state(
            _state(
                investment_plan="**Recommendation**: Buy",
                trader_investment_plan="**Action**: Buy",
                final_trade_decision="**Rating**: Buy",
            )
        )
        issue = next(issue for issue in result.issues if issue.code == "MULTIPLE_RECOMMENDATIONS")
        assert issue.severity == "warning"
        assert result.status == "research_only"

    def test_multiple_decision_recommendations_block_in_strict_mode(self):
        result = validate_final_state(
            _state(
                investment_plan="**Recommendation**: Buy",
                trader_investment_plan="**Action**: Buy",
                final_trade_decision="**Rating**: Buy",
            ),
            strict_mode=True,
        )
        issue = next(issue for issue in result.issues if issue.code == "MULTIPLE_RECOMMENDATIONS")
        assert issue.severity == "blocking"
        assert result.status == "blocked"
        assert any(issue.code == "UNAUTHORIZED_RECOMMENDATION" for issue in result.blocking_issues)

    def test_strict_mode_allows_only_final_trade_decision_rating(self):
        result = validate_final_state(
            _state(
                investment_plan="Research synthesis with no recommendation line.",
                trader_investment_plan="Trader execution context with no action line.",
                final_trade_decision="**Rating**: Hold\n\n**Executive Summary**: Balanced.",
            ),
            strict_mode=True,
        )
        assert not any(
            issue.code in {"UNAUTHORIZED_RECOMMENDATION", "MULTIPLE_RECOMMENDATIONS"}
            for issue in result.issues
        )

    def test_strict_mode_passes_rendered_non_authoritative_handoffs(self):
        investment_plan = (
            "**Evidence Balance**: Balanced\n\n"
            "**Bull Case Summary**: Supported positives are present.\n\n"
            "**Bear Case Summary**: Material risks remain.\n\n"
            "**Trader Context**: Neutral execution context for later review."
        )
        trader_context = (
            "**Execution Bias**: Neutral\n\n"
            "**Reasoning**: Execution context remains balanced."
        )
        final_decision = render_pm_decision(
            PortfolioDecision(
                rating=PortfolioRating.HOLD,
                executive_summary="Maintain current posture pending better evidence.",
                investment_thesis="The evidence is balanced and unresolved risks remain.",
            )
        )

        result = validate_final_state(
            _state(
                investment_plan=investment_plan,
                trader_investment_plan=trader_context,
                final_trade_decision=final_decision,
            ),
            strict_mode=True,
        )
        assert not result.has_blocking_issues

    def test_strict_mode_blocks_missing_final_rating(self):
        result = validate_final_state(
            _state(
                investment_plan="Research synthesis.",
                trader_investment_plan="Trader execution context.",
                final_trade_decision="Executive summary without rating.",
            ),
            strict_mode=True,
        )
        assert result.status == "blocked"
        assert any(issue.code == "FINAL_RECOMMENDATION_MISSING" for issue in result.blocking_issues)

    def test_dashboard_body_mismatch_blocks(self):
        result = validate_final_state(
            _state(
                final_trade_decision="**Rating**: Hold\n\n**Executive Summary**: Balanced.",
                dashboard_model={
                    "report_status": "research_only",
                    "recommendation": "Buy",
                    "action": "Use final Portfolio Manager rating: Buy",
                    "target_low": None,
                    "target_base": None,
                    "target_high": None,
                    "sentiment": None,
                    "current_price": None,
                    "price_currency": "USD",
                    "price_as_of": "2026-06-26",
                    "data_quality_score": 100,
                },
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "RESEARCH_ONLY_ACTION_CONFLICT" for issue in result.blocking_issues)

    def test_corrupted_output_blocks(self):
        result = validate_final_state(_state(news_report="Valid words " + "\x00" * 20))
        assert result.status == "blocked"
        assert any(issue.code == "CORRUPTED_AGENT_OUTPUT" for issue in result.blocking_issues)

    def test_ambiguous_instrument_blocks(self):
        result = validate_final_state(
            _state(
                instrument_resolution={
                    "requested_query": "SAAB A",
                    "status": "ambiguous",
                    "candidates": [],
                    "warnings": ["Ticker appears to include a free-form share class."],
                    "user_confirmation_required": True,
                }
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "INSTRUMENT_AMBIGUOUS" for issue in result.blocking_issues)

    def test_stale_market_data_blocks(self):
        result = validate_final_state(
            _state(
                market_data_freshness={
                    "ticker": "NVDA",
                    "requested_as_of": "2026-06-26",
                    "provider": "yfinance",
                    "market_data_session": "2026-05-07",
                    "sessions_stale": 35,
                    "freshness_status": "blocked",
                    "max_completed_sessions_old": 2,
                    "recommendation_allowed": False,
                    "warnings": ["Market data are 35 completed sessions old."],
                }
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "STALE_MARKET_DATA" for issue in result.blocking_issues)

    def test_stale_status_is_hard_recommendation_blocker(self):
        result = validate_final_state(
            _state(
                market_data_freshness={
                    "ticker": "NVDA",
                    "requested_as_of": "2026-06-26",
                    "provider": "yfinance",
                    "market_data_session": "2026-06-24",
                    "sessions_stale": 2,
                    "freshness_status": "stale",
                    "max_completed_sessions_old": 2,
                    "recommendation_allowed": True,
                    "warnings": ["Market data are stale."],
                }
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "STALE_MARKET_DATA" for issue in result.blocking_issues)

    def test_directional_rating_requires_verified_fundamentals(self):
        result = validate_final_state(
            _state(
                final_trade_decision="**Rating**: Overweight\n\n**Executive Summary**: Constructive.",
                fundamentals_report="No verified fundamentals were provided.",
            )
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "FUNDAMENTAL_EVIDENCE_MISSING"
            for issue in result.blocking_issues
        )

    def test_current_price_mismatch_blocks(self):
        result = validate_final_state(
            _state(
                market_data_freshness={
                    "ticker": "TSLA",
                    "requested_as_of": "2026-06-26",
                    "provider": "yfinance",
                    "market_data_session": "2026-06-26",
                    "sessions_stale": 0,
                    "freshness_status": "fresh",
                    "max_completed_sessions_old": 2,
                    "recommendation_allowed": True,
                    "analyzed_price": 340,
                    "current_price": 425,
                    "warnings": [],
                }
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "CURRENT_PRICE_MISMATCH" for issue in result.blocking_issues)

    def test_price_target_requires_valuation_method(self):
        result = validate_final_state(
            _state(
                final_trade_decision=(
                    "**Rating**: Hold\n\n"
                    "**Executive Summary**: Balanced.\n\n"
                    "**Price Target**: 425"
                )
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "VALUATION_METHOD_MISSING" for issue in result.blocking_issues)

    def test_vwma_absent_from_market_report_blocks(self):
        result = validate_final_state(
            _state(
                market_report="Market report covers RSI and MACD only.",
                final_trade_decision=(
                    "**Rating**: Hold\n\n"
                    "**Executive Summary**: VWMA confirms the setup."
                ),
            )
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "UNSUPPORTED_DECISION_INPUT"
            for issue in result.blocking_issues
        )

    def test_historical_lessons_require_auditable_evidence(self):
        result = validate_final_state(
            _state(
                final_trade_decision=(
                    "**Rating**: Hold\n\n"
                    "**Executive Summary**: Prior lessons support caution."
                )
            )
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "UNVERIFIED_LESSON_HISTORY"
            for issue in result.blocking_issues
        )

    def test_historical_lessons_pass_with_structured_evidence(self):
        result = validate_final_state(
            _state(
                final_trade_decision=(
                    "**Rating**: Hold\n\n"
                    "**Executive Summary**: Prior lessons support caution."
                ),
                historical_lessons_evidence=[_valid_lesson()],
            )
        )
        assert not any(
            issue.code == "UNVERIFIED_LESSON_HISTORY"
            for issue in result.issues
        )

    def test_invalid_historical_lesson_is_not_usable(self):
        assert not lesson_is_usable(
            _valid_lesson(validation_status="possible_leakage")
        )

    def test_duplicate_historical_lessons_are_excluded(self):
        lessons = usable_historical_lessons(
            _state(
                historical_lessons_evidence=[
                    _valid_lesson(lesson_id="L1", duplicate_group_id="dup-1"),
                    _valid_lesson(lesson_id="L2", duplicate_group_id="dup-1"),
                    _valid_lesson(lesson_id="L3", duplicate_group_id=None),
                ]
            )
        )
        assert [lesson.lesson_id for lesson in lessons] == ["L3"]

    def test_decision_evidence_bundle_records_usable_lessons_and_blockers(self):
        state = _state(
            historical_lessons_evidence=[_valid_lesson()],
            technical_validation={
                "rsi_divergence": {
                    "validated": True,
                    "event": "bullish_divergence",
                }
            },
        )
        validation = validate_final_state(state)
        bundle = build_decision_evidence_bundle(state, validation)
        assert "LESSON-NVDA-20260501" in bundle.validated_lesson_ids
        assert "metric:rsi_divergence" in bundle.validated_metric_ids
        assert bundle.unresolved_blocking_issues == []

    def test_claim_extraction_rejects_unsupported_downstream_claims(self):
        state = _state(
            investment_debate_state={
                "bull_history": "VWMA confirms the setup.",
                "bear_history": "This is a classic bearish divergence.",
                "judge_decision": "",
            },
            risk_debate_state={
                "aggressive_history": "Volume shows accumulation behavior.",
                "conservative_history": "",
                "neutral_history": "",
                "judge_decision": "",
            },
        )
        claims = rejected_claims(state)
        claim_types = {claim.claim_type for claim in claims}
        assert {
            "technical_metric_reference",
            "bearish_divergence",
            "volume_flow_inference",
        }.issubset(claim_types)
        assert all(not claim.publishable for claim in claims)

    def test_claim_extraction_verifies_supported_divergence_claim(self):
        state = _state(
            market_report="RSI shows a bullish divergence after the new low.",
            technical_validation={
                "rsi_divergence": {
                    "validated": True,
                    "event": "bullish_divergence",
                    "price_low_1": 30.71,
                    "price_low_2": 29.93,
                    "indicator_low_1": 35.26,
                    "indicator_low_2": 38.10,
                }
            },
        )
        claims = verified_claims(state)
        assert len(claims) == 1
        assert claims[0].claim_type == "bullish_divergence"
        assert claims[0].publishable is True

    def test_evidence_bundle_uses_verified_claim_ids(self):
        state = _state(
            market_report="RSI shows a bullish divergence after the new low.",
            technical_validation={
                "rsi_divergence": {
                    "validated": True,
                    "event": "bullish_divergence",
                }
            },
        )
        bundle = build_decision_evidence_bundle(state, validate_final_state(state))
        claim_ids = {claim.claim_id for claim in verified_claims(state)}
        assert set(bundle.verified_claim_ids) == claim_ids

    def test_unsupported_streak_claim_blocks(self):
        result = validate_final_state(
            _state(
                final_trade_decision=(
                    "**Rating**: Hold\n\n"
                    "**Executive Summary**: MACD histogram expanded for seven consecutive sessions."
                )
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "UNSUPPORTED_STREAK_CLAIM" for issue in result.blocking_issues)

    def test_directional_override_requires_new_verified_evidence(self):
        result = validate_final_state(
            _state(
                investment_plan="**Evidence Balance**: Balanced\n\n**Decision Permitted**: No",
                trader_investment_plan="**Execution Bias**: Neutral",
                final_trade_decision="**Rating**: Overweight\n\n**Executive Summary**: Override to add exposure.",
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "UNSUPPORTED_DECISION_OVERRIDE" for issue in result.blocking_issues)

    def test_rhetorical_language_blocks(self):
        result = validate_final_state(
            _state(
                risk_debate_state={
                    "aggressive_history": "The evidence is extremely compelling and risks clash violently.",
                    "conservative_history": "",
                    "neutral_history": "",
                    "judge_decision": "",
                }
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "RHETORICAL_LANGUAGE" for issue in result.blocking_issues)

    def test_duplicate_issue_codes_per_location_are_deduplicated(self):
        result = validate_final_state(
            _state(
                market_report=(
                    "The market has a death cross. "
                    "This death cross confirms structural weakness."
                )
            )
        )
        matching = [
            issue
            for issue in result.blocking_issues
            if issue.code == "MOVING_AVERAGE_CROSS_UNPROVEN"
            and issue.location == "market_report"
        ]
        assert len(matching) == 1

    def test_cross_context_reference_does_not_create_cross_claim(self):
        state = _state(
            market_report=(
                "The 200 SMA is included as Golden/Death Cross context only; "
                "no dated crossover event is asserted."
            )
        )
        result = validate_final_state(state)

        assert not any(
            issue.code == "MOVING_AVERAGE_CROSS_UNPROVEN"
            for issue in result.blocking_issues
        )
        assert not any(
            claim.claim_type == "moving_average_cross"
            for claim in rejected_claims(state)
        )

    def test_tsla_v3_bad_artifact_emits_expected_blockers(self):
        result = validate_final_state(
            _state(
                company_of_interest="TSLA",
                market_report="Market report covers RSI, MACD, ATR, and SMA only.",
                fundamentals_report="No verified fundamentals were provided.",
                investment_plan="**Evidence Balance**: Balanced\n\n**Decision Permitted**: No",
                trader_investment_plan="**Execution Bias**: Neutral",
                final_trade_decision=(
                    "**Rating**: Overweight\n\n"
                    "**Executive Summary**: Prior lessons and VWMA support adding exposure. "
                    "MACD histogram expanded for seven consecutive sessions.\n\n"
                    "**Investment Thesis**: This overrides neutral lower-level evidence.\n\n"
                    "**Price Target**: 425"
                ),
                market_data_freshness={
                    "ticker": "TSLA",
                    "requested_as_of": "2026-06-29",
                    "provider": "yfinance",
                    "market_data_session": "2026-05-07",
                    "sessions_stale": 35,
                    "freshness_status": "blocked",
                    "max_completed_sessions_old": 2,
                    "recommendation_allowed": False,
                    "analyzed_price": 398.73,
                    "current_price": 425.00,
                    "warnings": ["Market data are 35 completed sessions old."],
                },
                investment_debate_state={
                    "bull_history": "",
                    "bear_history": "This is a classic bearish divergence.",
                    "judge_decision": "",
                },
                risk_debate_state={
                    "aggressive_history": "Volume shows accumulation behavior.",
                    "conservative_history": "",
                    "neutral_history": "",
                    "judge_decision": "",
                },
                dashboard_model={
                    "report_status": "research_only",
                    "decision_status": "available",
                    "recommendation": "Overweight",
                    "action": "Use final Portfolio Manager rating: Overweight",
                    "target_low": None,
                    "target_base": 425,
                    "target_high": None,
                    "sentiment": None,
                    "current_price": None,
                    "price_currency": "USD",
                    "price_as_of": "2026-05-07",
                    "data_quality_score": 100,
                },
            )
        )
        codes = {issue.code for issue in result.blocking_issues}
        assert {
            "STALE_MARKET_DATA",
            "CURRENT_PRICE_MISMATCH",
            "RESEARCH_ONLY_ACTION_CONFLICT",
            "UNSUPPORTED_DECISION_INPUT",
            "FUNDAMENTAL_EVIDENCE_MISSING",
            "UNVERIFIED_LESSON_HISTORY",
            "FALSE_BEARISH_DIVERGENCE_CLAIM",
            "UNSUPPORTED_VOLUME_INFERENCE",
            "UNSUPPORTED_STREAK_CLAIM",
            "VALUATION_METHOD_MISSING",
            "UNSUPPORTED_DECISION_OVERRIDE",
        }.issubset(codes)


@pytest.mark.unit
class TestReportWriterValidation:
    def test_writes_validation_report(self, tmp_path):
        report_path = write_report_tree(
            _state(),
            "NVDA",
            tmp_path,
            expected_analysts=("market", "social", "news", "fundamentals"),
        )
        assert report_path.exists()

        validation_path = tmp_path / "validation_report.json"
        assert validation_path.exists()
        payload = json.loads(validation_path.read_text(encoding="utf-8"))
        assert payload["status"] == "research_only"

        dashboard_path = tmp_path / "dashboard.json"
        assert dashboard_path.exists()
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert dashboard["recommendation"] == "INSUFFICIENT_EVIDENCE"
        assert dashboard["decision_status"] == "blocked"
        assert dashboard["action"] == "NO_CURRENT_TRANSACTION"

        evidence_path = tmp_path / "decision_evidence_bundle.json"
        assert evidence_path.exists()
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert "report:final_trade_decision" in evidence["canonical_fact_ids"]

        lessons_path = tmp_path / "validated_lessons.json"
        assert lessons_path.exists()
        assert json.loads(lessons_path.read_text(encoding="utf-8")) == []

        verified_claims_path = tmp_path / "verified_claims.json"
        rejected_claims_path = tmp_path / "rejected_claims.json"
        assert verified_claims_path.exists()
        assert rejected_claims_path.exists()
        assert json.loads(verified_claims_path.read_text(encoding="utf-8")) == []
        assert json.loads(rejected_claims_path.read_text(encoding="utf-8")) == []

    def test_writes_supply_chain_section_file(self, tmp_path):
        report_path = write_report_tree(
            _state(supply_chain_report="### Supply Chain\nPer Vein Graph context."),
            "NVDA",
            tmp_path,
            expected_analysts=("market", "supply_chain"),
        )

        assert report_path.exists()
        supply_path = tmp_path / "1_analysts" / "supply_chain.md"
        assert supply_path.exists()
        assert "Per Vein Graph context" in supply_path.read_text(encoding="utf-8")

    def test_research_only_report_suppresses_directional_pm_decision(self, tmp_path):
        state = _state(
            final_trade_decision=(
                "**Rating**: Underweight\n\n"
                "**Executive Summary**: Reduce exposure based on incomplete evidence."
            ),
            risk_debate_state={
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "judge_decision": (
                    "**Rating**: Underweight\n\n"
                    "**Executive Summary**: Reduce exposure based on incomplete evidence."
                ),
            },
        )

        report_path = write_report_tree(state, "NVDA", tmp_path)
        complete_report = report_path.read_text(encoding="utf-8")
        published_decision = (tmp_path / "5_portfolio" / "decision.md").read_text(
            encoding="utf-8"
        )

        assert "**Rating**: Insufficient Evidence" in complete_report
        assert "**Action**: No current transaction" in complete_report
        assert "**Rating**: Underweight" not in complete_report
        assert "**Rating**: Underweight" not in published_decision

    def test_strict_validation_blocks_publication(self, tmp_path):
        with pytest.raises(ValueError, match="Report validation blocked publication"):
            write_report_tree(
                _state(
                    investment_plan="**Recommendation**: Buy",
                    trader_investment_plan="**Action**: Buy",
                    final_trade_decision="**Rating**: Buy",
                ),
                "NVDA",
                tmp_path,
                strict_validation=True,
            )

        validation_path = tmp_path / "validation_report.json"
        assert validation_path.exists()
        payload = json.loads(validation_path.read_text(encoding="utf-8"))
        assert payload["status"] == "blocked"


@pytest.mark.unit
class TestDashboardModel:
    def test_verified_dashboard_uses_final_pm_rating_and_target(self):
        state = _state(
            final_trade_decision=(
                "**Rating**: Overweight\n\n"
                "**Executive Summary**: Constructive.\n\n"
                "**Investment Thesis**: Evidence supports upside.\n\n"
                "**Price Target**: 215.50"
            )
        )
        validation = ValidationResult(status="verified")
        dashboard = build_dashboard_model(state, validation)
        assert dashboard.recommendation == "Overweight"
        assert str(dashboard.target_base) == "215.50"
        assert dashboard.pdf_metrics()["Recommendation"] == "Overweight"
        assert dashboard.pdf_metrics()["Target"] == "215.5"

    def test_research_only_dashboard_suppresses_actionable_rating(self):
        state = _state(
            final_trade_decision=(
                "**Rating**: Overweight\n\n"
                "**Executive Summary**: Constructive but not fully verified."
            )
        )
        validation = validate_final_state(state)
        dashboard = build_dashboard_model(state, validation)
        assert validation.status == "research_only"
        assert dashboard.recommendation == "INSUFFICIENT_EVIDENCE"
        assert dashboard.decision_status == "blocked"
        assert dashboard.action == "NO_CURRENT_TRANSACTION"
        assert dashboard.target_base is None

    def test_stale_market_data_dashboard_blocks_transaction(self):
        state = _state(
            final_trade_decision=(
                "**Rating**: Overweight\n\n"
                "**Executive Summary**: Favorable if data were current."
            ),
            market_data_freshness={
                "ticker": "TSLA",
                "requested_as_of": "2026-06-26",
                "provider": "yfinance",
                "market_data_session": "2026-05-07",
                "sessions_stale": 35,
                "freshness_status": "blocked",
                "max_completed_sessions_old": 2,
                "recommendation_allowed": False,
                "warnings": ["Technical data are stale."],
            },
        )
        validation = validate_final_state(state)
        dashboard = build_dashboard_model(state, validation)
        assert validation.status == "blocked"
        assert dashboard.recommendation == "INSUFFICIENT_EVIDENCE"
        assert dashboard.decision_status == "blocked"
        assert dashboard.action == "NO_CURRENT_TRANSACTION"


@pytest.mark.unit
class TestInstrumentResolution:
    def test_freeform_share_class_is_ambiguous(self):
        result = resolve_instrument("SAAB A")
        assert result.status == "ambiguous"
        assert result.user_confirmation_required is True

    def test_provider_symbol_substitution_requires_confirmation(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "symbol": "SAABY",
            "exchange": "PNK",
            "currency": "USD",
            "quoteType": "EQUITY",
        }
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = resolve_instrument("SAAB-B.ST")
        assert result.status == "resolved"
        assert result.user_confirmation_required is True
        assert "SAABY" in result.warnings[0]


@pytest.mark.unit
class TestMarketDataFreshness:
    def test_weekend_after_completed_session_is_fresh(self):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame(
            {"Close": [100.0]},
            index=pd.to_datetime(["2026-06-26"]),
        )
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = check_market_data_freshness("NVDA", "2026-06-27")
        assert result.market_data_session.isoformat() == "2026-06-26"
        assert result.sessions_stale == 0
        assert result.freshness_status == "fresh"

    def test_old_session_blocks(self):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame(
            {"Close": [100.0]},
            index=pd.to_datetime(["2026-05-07"]),
        )
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = check_market_data_freshness("NVDA", "2026-06-26", max_completed_sessions_old=2)
        assert result.freshness_status == "blocked"
        assert result.recommendation_allowed is False


@pytest.mark.unit
class TestNewsRetrieval:
    def test_vendor_news_success(self):
        mock_ticker = MagicMock()
        mock_ticker.get_news.return_value = [
            {
                "content": {
                    "title": "Company update",
                    "provider": {"displayName": "Wire"},
                    "pubDate": "2026-06-29T12:00:00Z",
                    "canonicalUrl": {"url": "https://example.com/news"},
                }
            }
        ]
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = check_news_retrieval("TSLA", "2026-06-29", "2026-06-30")

        assert result.status == "NEWS_VENDOR_SUCCESS"
        assert result.vendor_results_count == 1
        assert result.fallback_attempted is False

    def test_vendor_empty_uses_vein_peer_news(self):
        primary = MagicMock()
        primary.get_news.return_value = []
        peer = MagicMock()
        peer.get_news.return_value = [
            {
                "content": {
                    "title": "Lithium refining update",
                    "provider": {"displayName": "Wire"},
                    "pubDate": "2026-06-29T12:00:00Z",
                    "canonicalUrl": {"url": "https://example.com/peer-news"},
                }
            }
        ]

        def ticker_factory(symbol):
            return peer if symbol == "ALB" else primary

        with patch("yfinance.Ticker", side_effect=ticker_factory):
            result = check_news_retrieval(
                "TSLA",
                "2026-06-29",
                "2026-06-30",
                context_bundle={
                    "version": "vein-context-v1",
                    "primary_symbol": "TSLA",
                    "has_graph_coverage": True,
                    "peer_tickers_for_news": ["ALB"],
                },
            )

        assert result.status == "PEER_NEWS_FALLBACK_USED"
        assert result.peer_fallback_attempted is True
        assert result.peer_tickers_queried == ["ALB"]
        assert result.peer_results_count == 1
        assert result.results[0]["source_type"] == "vein_peer_news"
        assert result.results[0]["peer_ticker"] == "ALB"
        assert result.results[0]["supplemental_for"] == "primary_ticker_news_vacuum"
        assert result.fallback_attempted is False


@pytest.mark.unit
class TestTechnicalValidationFunctions:
    def test_saab_values_are_not_bullish_divergence(self):
        assert not bullish_divergence(
            price_low_1=30.71,
            price_low_2=29.93,
            indicator_low_1=35.26,
            indicator_low_2=34.96,
        )

    def test_bullish_divergence_requires_lower_price_and_higher_indicator(self):
        assert bullish_divergence(
            price_low_1=30.71,
            price_low_2=29.93,
            indicator_low_1=35.26,
            indicator_low_2=38.10,
        )

    def test_rsi_near_65_is_not_bearish_divergence(self):
        assert not bearish_divergence(
            price_high_1=400.62,
            price_high_2=398.73,
            indicator_high_1=60.31,
            indicator_high_2=64.60,
        )

    def test_macd_components_reconcile(self):
        assert macd_components_reconcile(macd_line=1.25, signal_line=0.75, histogram=0.5)
        assert not macd_components_reconcile(macd_line=1.25, signal_line=0.75, histogram=0.2)

    def test_detect_cross_returns_only_actual_event(self):
        golden = detect_cross([99, 101], [100, 100], dates=["2026-06-25", "2026-06-26"])
        static_above = detect_cross([101, 102], [100, 100], dates=["2026-06-25", "2026-06-26"])
        assert golden == {"event": "golden_cross", "event_date": "2026-06-26"}
        assert static_above == {"event": "no_new_cross", "event_date": None}

    def test_bollinger_squeeze_requires_full_band_width(self):
        assert bollinger_squeeze_valid(
            upper_band=110,
            middle_band=100,
            lower_band=90,
            width_percentile=0.08,
            threshold=0.10,
        )
        assert not bollinger_squeeze_valid(
            upper_band=110,
            middle_band=100,
            lower_band=None,
            width_percentile=0.08,
            threshold=0.10,
        )


@pytest.mark.unit
class TestTechnicalReportValidation:
    def test_bullish_divergence_claim_without_metadata_blocks(self):
        result = validate_final_state(
            _state(market_report="RSI shows a bullish divergence after the new low.")
        )
        assert result.status == "blocked"
        assert any(issue.code == "FALSE_BULLISH_DIVERGENCE_CLAIM" for issue in result.blocking_issues)

    def test_bullish_divergence_claim_with_validated_metadata_passes(self):
        result = validate_final_state(
            _state(
                market_report="RSI shows a bullish divergence after the new low.",
                technical_validation={
                    "rsi_divergence": {
                        "validated": True,
                        "event": "bullish_divergence",
                        "price_low_1": 30.71,
                        "price_low_2": 29.93,
                        "indicator_low_1": 35.26,
                        "indicator_low_2": 38.10,
                    }
                },
            )
        )
        assert not any(issue.code == "FALSE_BULLISH_DIVERGENCE_CLAIM" for issue in result.issues)

    def test_macd_mismatch_blocks(self):
        result = validate_final_state(
            _state(
                technical_validation={
                    "macd": {
                        "macd_line": 1.25,
                        "signal_line": 0.75,
                        "histogram": 0.20,
                    }
                }
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "MACD_COMPONENT_MISMATCH" for issue in result.blocking_issues)

    def test_bollinger_squeeze_claim_without_full_validation_blocks(self):
        result = validate_final_state(
            _state(market_report="The stock is in a Bollinger squeeze setup.")
        )
        assert result.status == "blocked"
        assert any(issue.code == "BOLLINGER_SQUEEZE_UNPROVEN" for issue in result.blocking_issues)

    def test_golden_cross_static_relationship_without_event_blocks(self):
        result = validate_final_state(
            _state(
                market_report="The chart has a golden cross configuration.",
                technical_validation={
                    "moving_average_cross": {
                        "event": "no_new_cross",
                        "event_date": None,
                    }
                },
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "MOVING_AVERAGE_CROSS_UNPROVEN" for issue in result.blocking_issues)

    def test_atr_optimized_stop_claim_blocks(self):
        result = validate_final_state(
            _state(market_report="The optimized stop is 2x ATR below entry.")
        )
        assert result.status == "blocked"
        assert any(issue.code == "ATR_SIZING_LOGIC_ERROR" for issue in result.blocking_issues)

    def test_bull_research_divergence_claim_blocks(self):
        result = validate_final_state(
            _state(
                investment_debate_state={
                    "bull_history": "RSI bullish divergence confirms upside.",
                    "bear_history": "",
                    "judge_decision": "",
                }
            )
        )
        assert result.status == "blocked"
        assert any(issue.code == "FALSE_BULLISH_DIVERGENCE_CLAIM" for issue in result.blocking_issues)

    def test_risk_volume_inference_claim_blocks(self):
        result = validate_final_state(
            _state(
                risk_debate_state={
                    "aggressive_history": "",
                    "conservative_history": "Volume shows accumulation behavior.",
                    "neutral_history": "",
                    "judge_decision": "",
                }
            )
        )
        assert result.status == "blocked"
        assert any(
            issue.code == "UNSUPPORTED_VOLUME_INFERENCE"
            for issue in result.blocking_issues
        )
