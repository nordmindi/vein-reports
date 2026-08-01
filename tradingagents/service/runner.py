from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.metrics import (
    ReportMetricsCallbackHandler,
    build_report_metrics,
    write_report_metrics,
)
from tradingagents.reporting import (
    finalize_validation_artifacts,
    generate_pdf_from_markdown,
    write_claim_reports,
    write_dashboard_report,
    write_decision_evidence_report,
    write_validation_report,
)
from tradingagents.integrations.intelligence_target import (
    IntelligenceTarget,
    is_equity_like_target,
    resolve_report_subject,
)
from tradingagents.service.tier_profiles import apply_tier_profile
from tradingagents.service.trace_logging import log_error, log_exception, log_info

logger = logging.getLogger(__name__)

VALID_ANALYSTS = {"market", "social", "news", "fundamentals", "supply_chain"}


@dataclass(frozen=True)
class ReportRequest:
    analysis_date: str
    ticker: str | None = None
    intelligence_target: IntelligenceTarget | None = None
    selected_analysts: tuple[str, ...] = ("market", "social", "news", "fundamentals")
    llm_provider: str | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    backend_url: str | None = None
    output_language: str | None = None
    max_debate_rounds: int | None = None
    max_risk_discuss_rounds: int | None = None
    checkpoint_enabled: bool | None = None
    user_id: str | None = None
    context_bundle: dict[str, Any] | None = None
    strategy_id: str | None = None
    report_tier: str = "pro"
    full_report: bool = False


@dataclass(frozen=True)
class ReportResult:
    job_id: str
    ticker: str
    analysis_date: str
    decision: Any
    report_dir: Path
    markdown_path: Path
    pdf_path: Path
    metrics: dict[str, Any] | None = None


def validate_report_request(request: ReportRequest) -> None:
    try:
        resolve_report_subject(ticker=request.ticker, target=request.intelligence_target)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    if request.ticker and request.intelligence_target:
        raise ValueError("provide either ticker or intelligence_target, not both")

    try:
        analysis_date = datetime.strptime(request.analysis_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("analysis_date must use YYYY-MM-DD format") from exc

    if analysis_date > datetime.now().date():
        raise ValueError("analysis_date cannot be in the future")

    if not request.selected_analysts:
        raise ValueError("at least one analyst is required")

    invalid = set(request.selected_analysts) - VALID_ANALYSTS
    if invalid:
        raise ValueError(f"unknown analysts: {', '.join(sorted(invalid))}")

    if request.max_debate_rounds is not None and request.max_debate_rounds < 1:
        raise ValueError("max_debate_rounds must be at least 1")

    if request.max_risk_discuss_rounds is not None and request.max_risk_discuss_rounds < 1:
        raise ValueError("max_risk_discuss_rounds must be at least 1")

    _validate_context_bundle(request)


def build_config(request: ReportRequest, job_id: str) -> dict[str, Any]:
    # Load environment variables directly to avoid import timing issues
    config = DEFAULT_CONFIG.copy()

    # Override with current environment variables to ensure we get the latest values
    config["llm_provider"] = os.getenv("TRADINGAGENTS_LLM_PROVIDER", config["llm_provider"])
    config["deep_think_llm"] = os.getenv("TRADINGAGENTS_DEEP_THINK_LLM", config["deep_think_llm"])
    config["quick_think_llm"] = os.getenv("TRADINGAGENTS_QUICK_THINK_LLM", config["quick_think_llm"])
    config["max_debate_rounds"] = int(os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", config["max_debate_rounds"]))
    config["max_risk_discuss_rounds"] = int(os.getenv("TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS", config["max_risk_discuss_rounds"]))

    report_root = Path(os.getenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", "reports/api")).resolve()
    cache_root = Path(os.getenv("TRADINGAGENTS_SERVICE_CACHE_DIR", ".tradingagents_service/cache")).resolve()
    memory_root = Path(os.getenv("TRADINGAGENTS_SERVICE_MEMORY_DIR", ".tradingagents_service/memory")).resolve()

    config["results_dir"] = str(report_root / "_logs" / job_id)
    config["data_cache_dir"] = str(cache_root)
    config["memory_log_path"] = str(memory_root / "trading_memory.md")
    config["vein_context_bundle"] = request.context_bundle or {}

    # Determine the final provider to use
    # Priority: 1. Request parameter, 2. Environment variable, 3. Auto-detection
    env_provider = config.get("llm_provider")
    env_deep_model = config.get("deep_think_llm")
    env_quick_model = config.get("quick_think_llm")

    logger.debug(f"Provider selection | Request provider: {request.llm_provider} | Env provider: {env_provider}")

    # Use request provider if specified
    if request.llm_provider is not None:
        config["llm_provider"] = request.llm_provider
        logger.debug(f"Using request-specified provider: {request.llm_provider}")
    # Use environment provider if specified and no request provider
    elif env_provider is not None:
        config["llm_provider"] = env_provider
        logger.debug(f"Using environment-configured provider: {env_provider}")
    # Auto-detect provider based on available API keys only if no provider is explicitly set
    else:
        logger.debug("No explicit provider set, auto-detecting based on API keys")
        openai_key = os.getenv("OPENAI_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")
        ollama_key = os.getenv("OLLAMA_API_KEY")

        logger.debug(f"API keys present | OpenAI: {bool(openai_key)} | Google: {bool(google_key)} | Ollama: {bool(ollama_key)}")

        if openai_key:
            logger.debug("Auto-selecting OpenAI provider due to presence of OPENAI_API_KEY")
            config["llm_provider"] = "openai"
            # Use more accessible models if the default ones aren't available
            if env_deep_model in ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-pro"] or env_deep_model is None:
                config["deep_think_llm"] = "gpt-4o-mini"
            if env_quick_model in ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-pro"] or env_quick_model is None:
                config["quick_think_llm"] = "gpt-4o-mini"
        elif google_key:
            logger.debug("Auto-selecting Google provider due to presence of GOOGLE_API_KEY")
            config["llm_provider"] = "google"
            if env_deep_model is None:
                config["deep_think_llm"] = "gemini-2.5-flash"
            if env_quick_model is None:
                config["quick_think_llm"] = "gemini-2.5-flash"
        elif ollama_key:
            logger.debug("Auto-selecting Ollama provider due to presence of OLLAMA_API_KEY")
            config["llm_provider"] = "ollama"
            if env_deep_model is None:
                config["deep_think_llm"] = "llama3.1:8b"
            if env_quick_model is None:
                config["quick_think_llm"] = "llama3.1:8b"
        else:
            logger.debug("Falling back to OpenAI provider")
            # Fallback to openai but with more accessible models
            config["llm_provider"] = "openai"
            if env_deep_model is None:
                config["deep_think_llm"] = "gpt-4o-mini"
            if env_quick_model is None:
                config["quick_think_llm"] = "gpt-4o-mini"

    # Ensure models are compatible with the selected provider
    final_provider = config["llm_provider"]
    if final_provider == "ollama":
        # For Ollama, set appropriate defaults if models aren't set or are incompatible
        if request.deep_think_llm is None and env_deep_model is None:
            config["deep_think_llm"] = "llama3.1:8b"
        elif request.deep_think_llm is None and env_deep_model is not None and env_provider == "ollama":
            # Keep the environment variable model for Ollama
            pass
        if request.quick_think_llm is None and env_quick_model is None:
            config["quick_think_llm"] = "llama3.1:8b"
        elif request.quick_think_llm is None and env_quick_model is not None and env_provider == "ollama":
            # Keep the environment variable model for Ollama
            pass
    elif final_provider == "google":
        # Set Google-specific defaults if not explicitly set in request
        if request.deep_think_llm is None and env_deep_model is None:
            config["deep_think_llm"] = "gemini-2.5-flash"
        if request.quick_think_llm is None and env_quick_model is None:
            config["quick_think_llm"] = "gemini-2.5-flash"
    elif final_provider == "openai":
        # Set OpenAI-specific defaults if not explicitly set in request
        if request.deep_think_llm is None and env_deep_model is None:
            config["deep_think_llm"] = "gpt-4o-mini"
        if request.quick_think_llm is None and env_quick_model is None:
            config["quick_think_llm"] = "gpt-4o-mini"

    overrides = {
        "llm_provider": request.llm_provider,
        "deep_think_llm": request.deep_think_llm,
        "quick_think_llm": request.quick_think_llm,
        "backend_url": request.backend_url,
        "output_language": request.output_language,
        "max_debate_rounds": request.max_debate_rounds,
        "max_risk_discuss_rounds": request.max_risk_discuss_rounds,
        "checkpoint_enabled": request.checkpoint_enabled,
    }
    for key, value in overrides.items():
        if value is not None:
            config[key] = value

    apply_tier_profile(config, request.report_tier)

    log_info(
        "report_config_built",
        jobId=job_id,
        reportTier=config.get("report_tier"),
        pipelineMode=config.get("pipeline_mode"),
        llmProvider=config.get("llm_provider"),
        deepThink=config.get("deep_think_llm"),
        quickThink=config.get("quick_think_llm"),
        maxToolRounds=config.get("max_tool_rounds_per_analyst"),
        backendUrl=config.get("backend_url") or os.getenv("OLLAMA_BASE_URL", "(provider default)"),
    )

    return config


def _validate_context_bundle(request: ReportRequest) -> None:
    bundle = request.context_bundle
    if bundle is None:
        return
    if not isinstance(bundle, dict):
        raise ValueError("context_bundle must be an object")

    primary_symbol = bundle.get("primary_symbol")
    subject = resolve_report_subject(ticker=request.ticker, target=request.intelligence_target)
    if (
        primary_symbol
        and request.intelligence_target is None
        and str(primary_symbol).strip().upper() != subject
    ):
        raise ValueError("context_bundle.primary_symbol must match ticker")

    for key in (
        "anchor_elements",
        "downstream_products",
        "related_companies",
        "chokepoints",
        "peer_tickers_for_news",
    ):
        value = bundle.get(key)
        if value is not None and not isinstance(value, list):
            raise ValueError(f"context_bundle.{key} must be a list")


def run_report_job(request: ReportRequest, job_id: str | None = None) -> ReportResult:
    """Run TradingAgents and produce markdown plus PDF artifacts."""
    load_dotenv()
    load_dotenv(".env.enterprise", override=False)
    validate_report_request(request)

    job_id = job_id or uuid4().hex
    ticker = resolve_report_subject(ticker=request.ticker, target=request.intelligence_target)
    equity_like = is_equity_like_target(request.intelligence_target)

    context_bundle = request.context_bundle
    if context_bundle is None and equity_like:
        from tradingagents.integrations.vein_explorer_client import (
            fetch_supply_chain_context,
            is_vein_pull_enabled,
        )

        if is_vein_pull_enabled():
            context_bundle = fetch_supply_chain_context(ticker)

    golden_trend_signal = None
    if equity_like:
        from tradingagents.integrations.golden_trend_client import fetch_signal_validation

        golden_trend_signal = fetch_signal_validation(ticker, strategy_id=request.strategy_id)

    intelligence_bundle = None
    intelligence_briefs = None
    from tradingagents.integrations.vein_aggregator_client import fetch_intelligence_bundle

    aggregator_symbol = (
        request.ticker.strip().upper()
        if request.ticker and request.intelligence_target is None
        else None
    )
    intelligence_bundle, intelligence_briefs = fetch_intelligence_bundle(
        aggregator_symbol,
        target=request.intelligence_target,
        end_date=request.analysis_date,
        context_bundle=context_bundle,
    )

    log_info("report_build_config", jobId=job_id, ticker=ticker)
    config = build_config(request, job_id)
    if context_bundle:
        config["vein_context_bundle"] = context_bundle
    if intelligence_bundle:
        config["vein_intelligence_bundle"] = intelligence_bundle
    if intelligence_briefs:
        config["vein_intelligence_briefs"] = intelligence_briefs
    if request.intelligence_target:
        config["vein_intelligence_target"] = request.intelligence_target.to_payload()
    config["golden_trend_signal"] = golden_trend_signal or {}
    config["llm_cache_namespace"] = f"{ticker}:{request.analysis_date}"

    log_info("report_graph_init", jobId=job_id, analysts=list(request.selected_analysts))
    metrics_handler = ReportMetricsCallbackHandler()
    graph = TradingAgentsGraph(
        selected_analysts=list(request.selected_analysts),
        debug=False,
        config=config,
        callbacks=[metrics_handler],
    )

    log_info(
        "report_propagation_started",
        jobId=job_id,
        ticker=ticker,
        analysisDate=request.analysis_date,
    )
    propagation_started = time.perf_counter()
    try:
        final_state, decision = graph.propagate(ticker, request.analysis_date)
        log_info("report_propagation_completed", jobId=job_id, decision=decision)
    except Exception as exc:
        error_msg = str(exc)
        if "insufficient_quota" in error_msg:
            user_friendly_error = "Service temporarily unavailable due to API quota limits. Please try again later or contact support."
            log_error("report_propagation_quota_failed", jobId=job_id)
            raise Exception(user_friendly_error) from None
        log_exception("report_propagation_failed", exc, jobId=job_id)
        raise

    if golden_trend_signal:
        final_state["golden_trend_signal"] = golden_trend_signal
    if config.get("vein_context_bundle"):
        final_state["vein_context_bundle"] = config.get("vein_context_bundle") or {}
    if config.get("vein_intelligence_bundle"):
        final_state["vein_intelligence_bundle"] = config.get("vein_intelligence_bundle") or {}
    if config.get("vein_intelligence_briefs"):
        final_state["vein_intelligence_briefs"] = config.get("vein_intelligence_briefs") or {}

    report_root = Path(os.getenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", "reports/api")).resolve()
    report_dir = report_root / job_id

    strict_validation = bool(config.get("strict_report_validation"))
    validation_result, dashboard_model = finalize_validation_artifacts(
        final_state,
        expected_analysts=request.selected_analysts,
        strict_validation=strict_validation,
    )
    if strict_validation and validation_result.has_blocking_issues:
        report_dir.mkdir(parents=True, exist_ok=True)
        write_validation_report(report_dir, validation_result)
        write_dashboard_report(report_dir, dashboard_model)
        write_decision_evidence_report(report_dir, final_state)
        write_claim_reports(report_dir, final_state)
        codes = ", ".join(issue.code for issue in validation_result.blocking_issues)
        raise ValueError(f"Report validation blocked publication: {codes}")

    log_info("report_save_started", jobId=job_id, reportDir=str(report_dir))
    markdown_path = graph.save_reports(
        final_state,
        ticker,
        report_dir,
        validation_result=validation_result,
        dashboard_model=dashboard_model,
        expected_analysts=request.selected_analysts,
        user_requested_full_report=request.full_report,
    )
    log_info("report_markdown_saved", jobId=job_id, path=str(markdown_path))

    log_info("report_pdf_generate_started", jobId=job_id, ticker=ticker)
    pdf_path = generate_pdf_from_markdown(
        markdown_path,
        ticker,
        report_dir / f"TradingAgents_Report_{ticker}_{job_id}.pdf",
        validation_result=validation_result,
        dashboard_model=dashboard_model,
    )
    log_info("report_pdf_generated", jobId=job_id, path=str(pdf_path))

    duration_sec = time.perf_counter() - propagation_started
    cache_stats = graph.llm_disk_cache.stats() if graph.llm_disk_cache else None
    metrics = build_report_metrics(
        job_id=job_id,
        ticker=ticker,
        analysis_date=request.analysis_date,
        handler=metrics_handler,
        config=config,
        duration_sec=duration_sec,
        selected_analysts=request.selected_analysts,
        llm_cache_stats=cache_stats,
    )
    write_report_metrics(report_dir, metrics)
    log_info(
        "report_metrics_recorded",
        jobId=job_id,
        llmCalls=metrics["usage"]["llm_calls"],
        toolCalls=metrics["usage"]["tool_calls"],
        tokensIn=metrics["usage"]["tokens_in"],
        tokensOut=metrics["usage"]["tokens_out"],
        estimatedCostUsd=metrics.get("estimated_cost_usd"),
        durationSec=metrics["duration_sec"],
    )

    return ReportResult(
        job_id=job_id,
        ticker=ticker,
        analysis_date=request.analysis_date,
        decision=decision,
        report_dir=report_dir,
        markdown_path=markdown_path,
        pdf_path=pdf_path,
        metrics=metrics,
    )

