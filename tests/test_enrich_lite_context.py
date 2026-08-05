"""Tests for optional lite context enrichment (Explorer / Aggregator / cache)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tradingagents.validation.enrich_lite_context import (
    briefs_to_intelligence_brief,
    enrich_lite_payload,
)
from tradingagents.validation.report_validation_lite import validate_report_lite


@pytest.mark.unit
class TestEnrichLiteContext:
    def test_caller_context_wins_over_fetch(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_LITE_EXPLORER_ENABLED", "1")
        monkeypatch.setenv("TRADINGAGENTS_LITE_AGGREGATOR_ENABLED", "1")

        def boom(*_args, **_kwargs):
            raise AssertionError("should not fetch when caller supplied context")

        monkeypatch.setattr(
            "tradingagents.validation.enrich_lite_context._fetch_explorer_context",
            boom,
        )
        monkeypatch.setattr(
            "tradingagents.validation.enrich_lite_context._fetch_intelligence_brief",
            boom,
        )

        payload = enrich_lite_payload(
            {
                "symbol": "NVDA",
                "supplyChainContext": {"has_graph_coverage": True, "chokepoints": ["fab"]},
                "intelligenceBrief": {"status": "ok", "bias": "BULLISH"},
                "reportContext": {"directionalBias": "BULLISH"},
            }
        )
        assert payload["_liteEnrichment"]["supplyChain"] == "caller"
        assert payload["_liteEnrichment"]["intelligence"] == "caller"
        assert payload["_liteEnrichment"]["reportContext"] == "caller"

    def test_explorer_and_aggregator_fill_when_enabled(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_LITE_EXPLORER_ENABLED", "1")
        monkeypatch.setenv("TRADINGAGENTS_LITE_AGGREGATOR_ENABLED", "1")
        monkeypatch.setattr(
            "tradingagents.validation.enrich_lite_context._fetch_explorer_context",
            lambda _symbol: {"has_graph_coverage": True, "chokepoints": ["port"]},
        )
        monkeypatch.setattr(
            "tradingagents.validation.enrich_lite_context._fetch_intelligence_brief",
            lambda _symbol: {"status": "ok", "directionalBias": "BULLISH", "summary": "risk-on"},
        )

        payload = enrich_lite_payload({"symbol": "NVDA", "rawSignal": "ENTER_LONG"})
        assert payload["supplyChainContext"]["chokepoints"] == ["port"]
        assert payload["intelligenceBrief"]["directionalBias"] == "BULLISH"
        assert payload["_liteEnrichment"]["supplyChain"] == "explorer"
        assert payload["_liteEnrichment"]["intelligence"] == "aggregator"

        result = validate_report_lite(
            {
                **payload,
                "finalSignal": "ENTER_LONG",
                "tradeAllowed": True,
                "confidenceScore": 80,
            }
        )
        assert result["reportValidation"]["status"] == "APPROVED"

    def test_sibling_failures_fail_open(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_LITE_EXPLORER_ENABLED", "1")
        monkeypatch.setenv("TRADINGAGENTS_LITE_AGGREGATOR_ENABLED", "1")
        monkeypatch.setattr(
            "tradingagents.validation.enrich_lite_context._fetch_explorer_context",
            lambda _symbol: None,
        )
        monkeypatch.setattr(
            "tradingagents.validation.enrich_lite_context._fetch_intelligence_brief",
            lambda _symbol: None,
        )
        payload = enrich_lite_payload(
            {
                "symbol": "FCX",
                "finalSignal": "ENTER_LONG",
                "tradeAllowed": True,
            }
        )
        assert payload["_liteEnrichment"]["supplyChain"] == "missing"
        assert payload["_liteEnrichment"]["intelligence"] == "missing"
        result = validate_report_lite(payload)
        assert result["reportValidation"]["recommendation"] == "NEUTRAL"

    def test_local_job_cache_supplies_report_context(self):
        record = SimpleNamespace(
            job_id="job-1",
            status=SimpleNamespace(value="completed"),
            request=SimpleNamespace(ticker="TSLA"),
            result=SimpleNamespace(decision="BUY", report_dir=None),
            completed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        payload = enrich_lite_payload({"symbol": "TSLA"}, jobs={"job-1": record})
        assert payload["reportContext"]["directionalBias"] == "BULLISH"
        assert payload["_liteEnrichment"]["reportContext"] == "local_cache"

    def test_briefs_to_intelligence_brief_maps_bands(self):
        brief = briefs_to_intelligence_brief(
            {"retrieval": {"status": "ok"}},
            {
                "sentiment": {"overall_band": "Bullish", "headline": "Positive tone"},
                "news": {"headline_sentiment_band": "Bullish"},
            },
        )
        assert brief is not None
        assert brief["directionalBias"] == "BULLISH"
        assert brief["status"] == "ok"
        assert "Positive" in brief["summary"]
