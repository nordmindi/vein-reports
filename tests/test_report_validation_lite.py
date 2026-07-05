"""Tests for report-validation-lite fusion endpoint logic."""

from __future__ import annotations

import pytest

from tradingagents.validation.report_validation_lite import validate_report_lite


@pytest.mark.unit
class TestReportValidationLite:
    def test_watchlist_signal_stays_blocked(self):
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
        assert report["recommendation"] == "INSUFFICIENT_EVIDENCE"
        assert report["status"] in {"BLOCKED", "MIXED"}

    def test_trade_allowed_with_confidence_can_approve(self):
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
        assert report["status"] == "APPROVED"
        assert report["directionalBias"] == "BULLISH"

    def test_positive_report_cannot_upgrade_blocked_signal(self):
        result = validate_report_lite(
            {
                "symbol": "FCX",
                "rawSignal": "ENTER_SHORT",
                "finalSignal": "BLOCKED",
                "tradeAllowed": False,
                "confidenceScore": 90,
                "topBlockers": ["TECHNICAL_PERMISSION_DENIED"],
            }
        )
        report = result["reportValidation"]
        assert report["recommendation"] == "INSUFFICIENT_EVIDENCE"
