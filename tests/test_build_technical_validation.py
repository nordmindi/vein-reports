"""Tests for technical_validation metadata builder."""

from __future__ import annotations

import pytest

from tradingagents.validation import validate_final_state
from tradingagents.validation.build_technical_validation import build_technical_validation
from tradingagents.validation.report_validator import _validate_market_data_freshness


@pytest.mark.unit
def test_stale_one_session_is_not_blocking():
    issues = _validate_market_data_freshness(
        {
            "market_data_freshness": {
                "freshness_status": "stale",
                "recommendation_allowed": True,
                "sessions_stale": 1,
                "warnings": ["Market data are 1 completed sessions old."],
            }
        }
    )
    assert issues == []


@pytest.mark.unit
def test_build_technical_validation_populates_core_fields():
    metadata = build_technical_validation("TSLA", "2026-07-30")
    assert "moving_average_cross" in metadata
    assert metadata["moving_average_cross"]["event"] in {
        "golden_cross",
        "death_cross",
        "no_new_cross",
    }
    assert "macd" in metadata
    assert "volume_inference" in metadata
    assert metadata["volume_inference"]["validated"] is True
    assert "streak_calculations" in metadata


@pytest.mark.unit
def test_technical_validation_unblocks_streak_and_volume_claims():
    from tests.test_report_validation import _state

    metadata = build_technical_validation("TSLA", "2026-07-30")
    state = _state(
        market_report=(
            "RSI has been below 30 for four consecutive oversold sessions."
        ),
        investment_debate_state={
            "bull_history": "",
            "bear_history": "Volume shows accumulation behavior on the bounce.",
            "judge_decision": "",
        },
        technical_validation=metadata,
    )
    result = validate_final_state(state)
    codes = {issue.code for issue in result.blocking_issues}
    assert "UNSUPPORTED_STREAK_CLAIM" not in codes
    assert "UNSUPPORTED_VOLUME_INFERENCE" not in codes


@pytest.mark.unit
def test_speculative_death_cross_language_does_not_block():
    from tests.test_report_validation import _state

    state = _state(
        market_report=(
            "The gap between the 50 SMA and 200 SMA is compressing, which "
            "historically precedes death cross formations when the shorter "
            "average crosses below the longer one."
        ),
        investment_debate_state={
            "bull_history": "The death cross approaching is not a sell signal.",
            "bear_history": "",
            "judge_decision": "",
        },
    )
    result = validate_final_state(state)
    assert not any(
        issue.code == "MOVING_AVERAGE_CROSS_UNPROVEN"
        for issue in result.blocking_issues
    )
