"""Tests for intelligence target helpers."""

from __future__ import annotations

import pytest

from tradingagents.integrations.intelligence_target import (
    IntelligenceTarget,
    build_thematic_instrument_context,
    is_equity_like_target,
    resolve_asset_type,
    resolve_display_label,
    resolve_report_subject,
)


@pytest.mark.unit
class TestIntelligenceTarget:
    def test_resolve_report_subject_from_ticker(self):
        assert resolve_report_subject(ticker="tsla", target=None) == "TSLA"

    def test_resolve_report_subject_from_sector_target(self):
        target = IntelligenceTarget(type="sector", value="mining")
        assert resolve_report_subject(ticker=None, target=target) == "MINING"

    def test_is_equity_like_defaults_true_without_target(self):
        assert is_equity_like_target(None) is True

    def test_is_equity_like_false_for_sector(self):
        assert is_equity_like_target(IntelligenceTarget(type="sector", value="mining")) is False

    def test_is_equity_like_true_for_crypto(self):
        assert is_equity_like_target(IntelligenceTarget(type="crypto", value="BTC")) is True

    def test_resolve_asset_type_for_sector(self):
        assert resolve_asset_type(IntelligenceTarget(type="sector", value="mining")) == "thematic"

    def test_build_thematic_instrument_context(self):
        text = build_thematic_instrument_context(
            subject="MINING",
            target=IntelligenceTarget(type="sector", value="mining"),
            primary_symbol="XME",
        )
        assert "mining" in text.lower()
        assert "XME" in text

    def test_resolve_display_label_from_target(self):
        label = resolve_display_label(
            subject="MINING",
            target=IntelligenceTarget(type="sector", value="mining"),
        )
        assert "Mining" in label
        assert "sector" in label
