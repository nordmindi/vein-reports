"""Tests for Golden Trend signal client normalization."""

from __future__ import annotations

import pytest

from tradingagents.integrations.golden_trend_client import normalize_signal_result


@pytest.mark.unit
class TestGoldenTrendClient:
    def test_normalize_watchlist_blocks_publication(self):
        normalized = normalize_signal_result(
            {
                "asset": "FCX",
                "strategy": "golden-trend-aggressive",
                "rawSignal": "ENTER_SHORT",
                "finalSignal": "WATCHLIST_ONLY",
                "tradeAllowed": False,
                "confidenceScore": 16,
                "confidenceGrade": "F",
                "validation": {"flags": ["PROPOSAL_GATE_FAILED"]},
                "decisionAudit": {"hardBlocks": ["PROPOSAL_GATE_FAILED"]},
            }
        )
        assert normalized["blocksTradePublication"] is True
        assert normalized["executable"] is False

    def test_normalize_executable_signal(self):
        normalized = normalize_signal_result(
            {
                "asset": "BTC-USD",
                "rawSignal": "ENTER_LONG",
                "finalSignal": "ENTER_LONG",
                "tradeAllowed": True,
                "confidenceScore": 80,
                "confidenceGrade": "B",
                "validation": {"flags": []},
                "decisionAudit": {},
            }
        )
        assert normalized["executable"] is True
        assert normalized["blocksTradePublication"] is False
