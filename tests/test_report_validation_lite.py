"""Tests for report-validation-lite fusion endpoint logic."""

from __future__ import annotations

import pytest

from tradingagents.validation.report_validation_lite import validate_report_lite


@pytest.mark.unit
class TestReportValidationLite:
    def test_watchlist_signal_defers_to_signals(self):
        result = validate_report_lite(
            {
                "symbol": "FCX",
                "rawSignal": "ENTER_SHORT",
                "finalSignal": "WATCHLIST_ONLY",
                "tradeAllowed": False,
                "confidenceScore": 16,
                "topBlockers": ["PROPOSAL_GATE_FAILED"],
            }
        )
        report = result["reportValidation"]
        assert report["recommendation"] == "DEFER_TO_SIGNALS"
        assert report["status"] == "DEFERRED"
        assert report["hardBlocks"] == []

    def test_trade_allowed_without_context_is_neutral(self):
        result = validate_report_lite(
            {
                "symbol": "BTC-USD",
                "rawSignal": "ENTER_LONG",
                "finalSignal": "ENTER_LONG",
                "tradeAllowed": True,
                "confidenceScore": 78,
            }
        )
        report = result["reportValidation"]
        assert report["status"] == "NO_CONTEXT"
        assert report["recommendation"] == "NEUTRAL"

    def test_supporting_cached_bias_approves(self):
        result = validate_report_lite(
            {
                "symbol": "BTC-USD",
                "rawSignal": "ENTER_LONG",
                "finalSignal": "ENTER_LONG",
                "tradeAllowed": True,
                "confidenceScore": 78,
                "reportContext": {"directionalBias": "BULLISH"},
            }
        )
        report = result["reportValidation"]
        assert report["status"] == "APPROVED"
        assert report["directionalBias"] == "BULLISH"
        assert report["supportingPoints"]

    def test_event_risk_hard_blocks(self):
        result = validate_report_lite(
            {
                "symbol": "FCX",
                "rawSignal": "ENTER_LONG",
                "finalSignal": "ENTER_LONG",
                "tradeAllowed": True,
                "confidenceScore": 80,
                "intelligenceBrief": {"status": "ok", "eventRisk": True, "bias": "BULLISH"},
            }
        )
        report = result["reportValidation"]
        assert report["status"] == "BLOCKED"
        assert report["recommendation"] == "INSUFFICIENT_EVIDENCE"
        assert report["hardBlocks"]

    def test_positive_report_cannot_upgrade_blocked_signal(self):
        result = validate_report_lite(
            {
                "symbol": "FCX",
                "rawSignal": "ENTER_SHORT",
                "finalSignal": "BLOCKED",
                "tradeAllowed": False,
                "confidenceScore": 90,
                "topBlockers": ["TECHNICAL_PERMISSION_DENIED"],
                "reportContext": {"directionalBias": "BEARISH"},
            }
        )
        report = result["reportValidation"]
        assert report["recommendation"] == "DEFER_TO_SIGNALS"
        assert report["status"] == "DEFERRED"
