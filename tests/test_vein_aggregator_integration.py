"""Tests for Vein Aggregator client and bundle formatting."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.integrations.intelligence_bundle_format import (
    format_news_analyst_context,
    format_news_block,
    format_news_headline_sentiment,
    format_reddit_block,
    format_retrieval_quality_note,
    format_sentiment_brief_header,
    format_stocktwits_block,
    has_intelligence_bundle,
    resolve_bundle_subject_label,
    section_status,
)
from tradingagents.integrations.intelligence_target import IntelligenceTarget
from tradingagents.integrations.vein_aggregator_client import (
    fetch_intelligence_bundle,
    is_vein_aggregator_enabled,
)

FIXTURE = Path(__file__).parent / "fixtures" / "intelligence_bundle_v1.json"

BRIEFS = {
    "sentiment": {
        "overall_band": "Bullish",
        "overall_score": 7.5,
        "confidence": "medium",
        "narrative": "Retail skews bullish on StockTwits.",
    },
    "news": {
        "summary": "Headlines focus on AI demand.",
        "headline_sentiment_band": "Somewhat-Bullish",
        "headline_sentiment_score": 0.35,
        "articles_with_sentiment": 1,
    },
}


@pytest.fixture
def bundle() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestIntelligenceBundleFormat:
    def test_fixture_contract_keys(self, bundle):
        assert bundle["version"] == "vein-intelligence-v1"
        assert "news" in bundle and "social" in bundle and "retrieval" in bundle
        assert "news_retrieval" in bundle["retrieval"]
        assert "sections" in bundle["retrieval"]
        assert bundle["retrieval"]["sections"]["news"]["status"] == "ok"

    def test_has_intelligence_bundle(self, bundle):
        assert has_intelligence_bundle({"vein_intelligence_bundle": bundle}) is True
        assert has_intelligence_bundle({}) is False

    def test_format_news_block(self, bundle):
        text = format_news_block(bundle, "NVDA")
        assert "NVIDIA AI demand remains strong" in text
        assert "Vein Aggregator" in text

    def test_format_news_block_uses_target_label(self, bundle):
        sector_bundle = copy.deepcopy(bundle)
        sector_bundle["target"] = {"type": "sector", "value": "mining"}
        sector_bundle["primary_symbol"] = "XME"
        sector_bundle["retrieval"]["news_retrieval"] = {
            "target_label": "Mining sector",
            "target_type": "sector",
            "target_value": "mining",
        }
        text = format_news_block(sector_bundle, "MINING")
        assert "## mining (sector) News (Vein Aggregator)" in text

    def test_resolve_bundle_subject_label_prefers_target(self, bundle):
        sector_bundle = copy.deepcopy(bundle)
        sector_bundle["target"] = {"type": "commodity", "value": "gold"}
        assert resolve_bundle_subject_label(sector_bundle, "GLD") == "gold (commodity)"

    def test_format_news_block_empty_section(self, bundle):
        empty = copy.deepcopy(bundle)
        empty["retrieval"]["sections"]["news"]["status"] = "empty"
        empty["retrieval"]["sections"]["news"]["item_count"] = 0
        text = format_news_block(empty, "NVDA")
        assert "<no news data collected>" in text
        assert "NVIDIA AI demand remains strong" not in text

    def test_format_stocktwits_block(self, bundle):
        text = format_stocktwits_block(bundle)
        assert "Bullish" in text

    def test_format_stocktwits_block_empty_social(self, bundle):
        empty = copy.deepcopy(bundle)
        empty["retrieval"]["sections"]["social"]["status"] = "empty"
        empty["retrieval"]["sections"]["social"]["item_count"] = 0
        text = format_stocktwits_block(empty)
        assert "<no social data collected>" in text

    def test_format_reddit_rate_limited(self, bundle):
        limited = copy.deepcopy(bundle)
        limited["retrieval"]["sections"]["social"]["status"] = "partial"
        limited["retrieval"]["sections"]["social"]["warnings"] = ["Reddit failed: 429"]
        limited["social"]["reddit_summary"] = "<Reddit temporarily rate-limited>"
        text = format_reddit_block(limited)
        assert "rate limiting" in text.lower()

    def test_format_retrieval_quality_note(self, bundle):
        text = format_retrieval_quality_note(bundle)
        assert "Retrieval status: ok" in text
        assert "news=ok" in text

    def test_format_sentiment_brief_header(self):
        text = format_sentiment_brief_header(BRIEFS)
        assert "Bullish" in text
        assert "Retail skews bullish" in text

    def test_format_news_headline_sentiment(self):
        text = format_news_headline_sentiment(BRIEFS)
        assert "Somewhat-Bullish" in text
        assert "0.35" in text

    def test_format_news_analyst_context_with_briefs(self, bundle):
        text = format_news_analyst_context(bundle, "NVDA", briefs=BRIEFS)
        assert "Vein Aggregator" in text
        assert "NVIDIA AI demand remains strong" in text
        assert "Headline sentiment" in text
        assert "Retrieval status: ok" in text

    def test_format_news_analyst_context_includes_article_sentiment(self, bundle):
        enriched = copy.deepcopy(bundle)
        enriched["news"]["primary"][0]["sentiment_label"] = "Bullish"
        enriched["news"]["primary"][0]["sentiment_score"] = 0.42
        text = format_news_analyst_context(enriched, "NVDA")
        assert "Sentiment: Bullish (+0.42)" in text

    def test_section_status_defaults_ok_without_sections(self):
        minimal = {"retrieval": {}}
        assert section_status(minimal, "news") == "ok"


class TestVeinAggregatorClient:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED", raising=False)
        monkeypatch.delenv("TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL", raising=False)
        assert is_vein_aggregator_enabled() is False
        assert fetch_intelligence_bundle("NVDA", end_date="2026-07-31") == (None, None)

    def test_fetch_when_enabled(self, monkeypatch, bundle):
        monkeypatch.setenv("TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED", "1")
        monkeypatch.setenv("TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL", "http://aggregator.test")
        monkeypatch.setenv("TRADINGAGENTS_VEIN_AGGREGATOR_API_KEY", "test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "intelligence_bundle": bundle,
            "briefs": BRIEFS,
        }

        with patch("tradingagents.integrations.vein_aggregator_client.requests.post") as post:
            post.return_value = mock_response
            result_bundle, result_briefs = fetch_intelligence_bundle(
                "NVDA",
                end_date="2026-07-31",
                context_bundle={
                    "has_graph_coverage": True,
                    "peer_tickers_for_news": ["AMD"],
                },
            )

        assert result_bundle is not None
        assert result_bundle["version"] == "vein-intelligence-v1"
        assert result_briefs is not None
        assert result_briefs["sentiment"]["overall_band"] == "Bullish"
        post.assert_called_once()
        call_url = post.call_args.args[0]
        assert call_url.endswith("/v1/feeds/intelligence/briefs")
        payload = post.call_args.kwargs["json"]
        assert payload["symbol"] == "NVDA"
        assert payload["briefs"] == ["sentiment", "news"]
        assert "AMD" in payload["peer_symbols"]

    def test_fetch_sector_target_payload(self, monkeypatch, bundle):
        monkeypatch.setenv("TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED", "1")
        monkeypatch.setenv("TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL", "http://aggregator.test")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"intelligence_bundle": bundle, "briefs": BRIEFS}

        target = IntelligenceTarget(type="sector", value="mining")
        with patch("tradingagents.integrations.vein_aggregator_client.requests.post") as post:
            post.return_value = mock_response
            fetch_intelligence_bundle(
                None,
                target=target,
                end_date="2026-07-31",
            )

        payload = post.call_args.kwargs["json"]
        assert "symbol" not in payload
        assert payload["target"] == {"type": "sector", "value": "mining"}


class TestTradingGraphNewsRetrieval:
    def test_uses_bundle_news_retrieval_when_present(self, bundle):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.config = {"vein_intelligence_bundle": bundle}
        resolved = graph._resolve_news_retrieval("NVDA", "2026-07-31")
        assert resolved["status"] == "NEWS_VENDOR_SUCCESS"
        assert resolved["vendor_results_count"] == 1
