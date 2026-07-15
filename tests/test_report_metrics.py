import pytest

from tradingagents.metrics.callback_handler import ReportMetricsCallbackHandler
from tradingagents.metrics.cost_estimator import (
    estimate_model_cost_usd,
    estimate_usage_cost_usd,
    load_model_pricing,
)
from tradingagents.metrics.report_metrics import (
    METRICS_FILENAME,
    build_report_metrics,
    write_report_metrics,
)


@pytest.mark.unit
class TestCostEstimator:
    def test_estimates_gpt4o_mini_cost(self):
        cost = estimate_model_cost_usd("gpt-4o-mini", tokens_in=1_000_000, tokens_out=1_000_000)
        assert cost == pytest.approx(0.75)

    def test_prefix_matches_versioned_model_ids(self):
        cost = estimate_model_cost_usd(
            "gpt-4o-mini-2024-07-18",
            tokens_in=1_000_000,
            tokens_out=0,
        )
        assert cost == pytest.approx(0.15)

    def test_unknown_model_returns_none(self):
        assert estimate_model_cost_usd("local-custom-model", 1000, 1000) is None

    def test_usage_total_aggregates_known_models(self):
        total, breakdown, source = estimate_usage_cost_usd(
            {
                "gpt-4o-mini": {"llm_calls": 3, "tokens_in": 100_000, "tokens_out": 20_000},
                "gpt-4o": {"llm_calls": 1, "tokens_in": 50_000, "tokens_out": 10_000},
            }
        )
        assert source == "default"
        assert total == pytest.approx(0.252)
        assert breakdown["gpt-4o-mini"] == pytest.approx(0.027)
        assert breakdown["gpt-4o"] == pytest.approx(0.225)

    def test_load_pricing_from_env(self, monkeypatch):
        monkeypatch.setenv(
            "TRADINGAGENTS_MODEL_PRICING_JSON",
            '{"custom-model": {"input_per_million": 1.0, "output_per_million": 2.0}}',
        )
        table, source = load_model_pricing()
        assert source == "env"
        assert table["custom-model"]["input_per_million"] == 1.0


@pytest.mark.unit
class TestReportMetrics:
    def test_build_and_write_metrics_artifact(self, tmp_path):
        handler = ReportMetricsCallbackHandler()
        handler.llm_calls = 2
        handler.tool_calls = 1
        handler.tokens_in = 1200
        handler.tokens_out = 400
        handler.by_model = {
            "gpt-4o-mini": {
                "llm_calls": 2,
                "tokens_in": 1200,
                "tokens_out": 400,
            }
        }

        metrics = build_report_metrics(
            job_id="job-123",
            ticker="TSLA",
            analysis_date="2026-07-15",
            handler=handler,
            config={
                "llm_provider": "openai",
                "deep_think_llm": "gpt-4o-mini",
                "quick_think_llm": "gpt-4o-mini",
            },
            duration_sec=42.5,
            selected_analysts=("market", "news"),
        )

        assert metrics["version"] == "report-metrics-v1"
        assert metrics["usage"]["llm_calls"] == 2
        assert metrics["estimated_cost_usd"] is not None

        path = write_report_metrics(tmp_path, metrics)
        assert path.name == METRICS_FILENAME
        assert path.exists()
