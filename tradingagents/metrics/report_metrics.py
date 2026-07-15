from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingagents.metrics.callback_handler import ReportMetricsCallbackHandler
from tradingagents.metrics.cost_estimator import estimate_usage_cost_usd

REPORT_METRICS_VERSION = "report-metrics-v1"
METRICS_FILENAME = "cost_metrics.json"


def build_report_metrics(
    *,
    job_id: str,
    ticker: str,
    analysis_date: str,
    handler: ReportMetricsCallbackHandler,
    config: dict[str, Any],
    duration_sec: float,
    selected_analysts: tuple[str, ...] | list[str],
    llm_cache_stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    stats = handler.get_stats()
    by_model = stats.get("by_model") or {}
    estimated_total, cost_by_model, pricing_source = estimate_usage_cost_usd(by_model)

    by_model_out: dict[str, Any] = {}
    for model_name, usage in by_model.items():
        by_model_out[model_name] = {
            **usage,
            "estimated_cost_usd": cost_by_model.get(model_name),
        }

    metrics: dict[str, Any] = {
        "version": REPORT_METRICS_VERSION,
        "job_id": job_id,
        "ticker": ticker,
        "analysis_date": analysis_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": round(duration_sec, 3),
        "report_tier": config.get("report_tier"),
        "pipeline_mode": config.get("pipeline_mode"),
        "llm_provider": config.get("llm_provider"),
        "models_configured": {
            "deep": config.get("deep_think_llm"),
            "quick": config.get("quick_think_llm"),
        },
        "selected_analysts": list(selected_analysts),
        "usage": {
            "llm_calls": stats["llm_calls"],
            "tool_calls": stats["tool_calls"],
            "tokens_in": stats["tokens_in"],
            "tokens_out": stats["tokens_out"],
        },
        "by_model": by_model_out,
        "estimated_cost_usd": estimated_total,
        "cost_estimation": {
            "method": "model_pricing_table",
            "pricing_source": pricing_source,
            "note": (
                "Estimate only; actual provider billing may differ. "
                "Local/self-hosted models may report zero tokens."
            ),
        },
    }
    if llm_cache_stats is not None:
        metrics["llm_cache"] = llm_cache_stats
    return metrics


def write_report_metrics(report_dir: Path, metrics: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / METRICS_FILENAME
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return path


def read_report_metrics(report_dir: Path) -> dict[str, Any] | None:
    path = report_dir / METRICS_FILENAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
