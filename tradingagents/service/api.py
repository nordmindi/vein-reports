from __future__ import annotations

import json
import os
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradingagents.integrations.intelligence_target import IntelligenceTarget, resolve_report_subject

from tradingagents.service.runner import (
    ReportRequest,
    ReportResult,
    run_report_job,
    validate_report_request,
)
from tradingagents.service.trace_logging import (
    bind_trace,
    bind_trace_from_mapping,
    current_trace,
    log_error,
    log_exception,
    log_info,
    log_warning,
    reset_trace,
)
from tradingagents.service.trace_middleware import TraceMiddleware

# Load environment variables
load_dotenv()
load_dotenv(".env.enterprise", override=False)

class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReportTier(str, Enum):
    free = "free"
    pro = "pro"


class VeinCompany(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = Field(default=None, examples=["Tesla, Inc."])
    symbol: str | None = Field(default=None, examples=["TSLA"])
    is_chokepoint: bool | None = Field(default=None)


class VeinAnchorElement(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., examples=["Electric vehicles"])


class VeinDownstreamProduct(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., examples=["EV battery packs"])
    category: str | None = Field(default=None, examples=["energy"])
    hops: int | None = Field(default=None, ge=0, examples=[1])
    is_chokepoint: bool | None = Field(default=None)


class VeinRelatedCompany(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = Field(..., examples=["ALB"])
    name: str | None = Field(default=None, examples=["Albemarle Corporation"])
    via: str | None = Field(default=None, examples=["Lithium refining"])
    via_chokepoint: bool | None = Field(default=None)


class VeinChokepoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., examples=["Lithium refining"])
    category: str | None = Field(default=None, examples=["materials"])
    hops: int | None = Field(default=None, ge=0, examples=[1])
    via: str | None = Field(default=None, examples=["ALB"])


class VeinContextBundle(BaseModel):
    """Supply-chain context supplied by Vein Explorer."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "version": "vein-context-v1",
                "primary_symbol": "TSLA",
                "has_graph_coverage": True,
                "company": {
                    "name": "Tesla, Inc.",
                    "symbol": "TSLA",
                    "is_chokepoint": False,
                },
                "anchor_elements": [{"name": "Electric vehicles"}],
                "downstream_products": [
                    {
                        "name": "EV battery packs",
                        "category": "energy",
                        "hops": 1,
                        "is_chokepoint": True,
                    }
                ],
                "related_companies": [
                    {
                        "symbol": "ALB",
                        "name": "Albemarle Corporation",
                        "via": "Lithium refining",
                        "via_chokepoint": True,
                    }
                ],
                "chokepoints": [
                    {"name": "EV battery packs", "category": "energy", "hops": 1},
                    {"name": "Lithium refining", "category": None, "hops": 0, "via": "ALB"},
                ],
                "peer_tickers_for_news": ["ALB"],
                "watchlist_notes": "Focus on margin and battery supply",
                "generated_at": "2026-06-30T18:00:00.000Z",
            }
        },
    )

    version: str = Field(default="vein-context-v1", examples=["vein-context-v1"])
    primary_symbol: str = Field(..., examples=["TSLA"])
    has_graph_coverage: bool = Field(
        ...,
        description="True when Vein Graph has structural coverage for the ticker.",
    )
    company: VeinCompany | None = None
    anchor_elements: list[VeinAnchorElement] = Field(default_factory=list)
    downstream_products: list[VeinDownstreamProduct] = Field(default_factory=list)
    related_companies: list[VeinRelatedCompany] = Field(default_factory=list)
    chokepoints: list[VeinChokepoint] = Field(default_factory=list)
    peer_tickers_for_news: list[str] = Field(
        default_factory=list,
        description="Supplemental peer symbols used only when primary news coverage is thin.",
        examples=[["ALB", "LIT"]],
    )
    watchlist_notes: str | None = Field(
        default=None,
        description="User-authored Vein watchlist notes. Use only as framing, not verified evidence.",
    )
    generated_at: str | None = Field(default=None, examples=["2026-06-30T18:00:00.000Z"])


class IntelligenceTargetInput(BaseModel):
    type: str = Field(
        ...,
        description="Target category: equity, commodity, sector, index, or crypto",
        examples=["sector"],
    )
    value: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Ticker, commodity, sector, or index name",
        examples=["mining"],
    )

    def to_target(self) -> IntelligenceTarget:
        target_type = self.type.strip().lower()
        if target_type not in ("equity", "commodity", "sector", "index", "crypto"):
            raise ValueError(
                "target.type must be one of: equity, commodity, sector, index, crypto"
            )
        return IntelligenceTarget(type=target_type, value=self.value.strip())


class CreateReportRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ticker": "NVDA",
                    "analysis_date": "2026-05-07",
                    "report_tier": "pro",
                    "selected_analysts": ["market", "social", "news", "fundamentals"],
                    "llm_provider": "ollama",
                    "deep_think_llm": "glm-5.2:cloud",
                    "quick_think_llm": "glm-5.2:cloud",
                    "max_debate_rounds": 1,
                    "max_risk_discuss_rounds": 1,
                    "output_language": "English",
                    "user_id": "saas-user-id",
                },
                {
                    "target": {"type": "sector", "value": "mining"},
                    "analysis_date": "2026-07-31",
                    "report_tier": "pro",
                    "selected_analysts": ["market", "social", "news"],
                },
                {
                    "ticker": "TSLA",
                    "analysis_date": "2026-06-30",
                    "report_tier": "pro",
                    "context_bundle": {
                        "version": "vein-context-v1",
                        "primary_symbol": "TSLA",
                        "has_graph_coverage": True,
                        "company": {
                            "name": "Tesla, Inc.",
                            "symbol": "TSLA",
                            "is_chokepoint": False,
                        },
                        "anchor_elements": [{"name": "Electric vehicles"}],
                        "downstream_products": [],
                        "related_companies": [],
                        "chokepoints": [],
                        "peer_tickers_for_news": [],
                        "watchlist_notes": None,
                        "generated_at": "2026-06-30T18:00:00.000Z",
                    },
                },
            ]
        }
    )

    ticker: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        description="Equity ticker for the report subject. Omit when using `target`.",
        examples=["NVDA"],
    )
    target: IntelligenceTargetInput | None = Field(
        default=None,
        description="Thematic intelligence target for sector/commodity/index/crypto aggregation.",
    )
    analysis_date: str | None = Field(
        default=None,
        description="Analysis date in YYYY-MM-DD format. Defaults to the service date.",
        examples=["2026-05-07"],
    )
    selected_analysts: list[str] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals"],
        description="Allowed values: market, social, news, fundamentals, supply_chain.",
        examples=[["market", "social", "news", "fundamentals"]],
    )
    llm_provider: str | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    backend_url: str | None = None
    output_language: str | None = None
    max_debate_rounds: int | None = Field(default=None, ge=1)
    max_risk_discuss_rounds: int | None = Field(default=None, ge=1)
    checkpoint_enabled: bool | None = None
    user_id: str | None = Field(default=None, max_length=128)
    report_tier: ReportTier = Field(
        default=ReportTier.pro,
        description="Free tier runs only the market analyst. Pro tier supports all analysts and VEIN context.",
    )
    context_bundle: VeinContextBundle | None = Field(
        default=None,
        description=(
            "Optional VEIN supply-chain context. For pro jobs, supplying this automatically "
            "adds the supply_chain analyst if it was not selected."
        ),
    )
    strategy_id: str | None = Field(
        default=None,
        description="Optional Vein Signals strategy profile for signal validation.",
        examples=["golden-trend-balanced"],
    )
    full_report: bool = Field(
        default=False,
        description=(
            "When true, publish FULL report mode with an appendix containing raw analyst, "
            "debate, and portfolio outputs."
        ),
    )

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_subject(self) -> Self:
        has_ticker = bool(self.ticker and self.ticker.strip())
        has_target = self.target is not None
        if not has_ticker and not has_target:
            raise ValueError("either ticker or target is required")
        if has_ticker and has_target:
            raise ValueError("provide either ticker or target, not both")
        return self

    @field_validator("selected_analysts")
    @classmethod
    def normalize_analysts(cls, value: list[str]) -> list[str]:
        return [item.strip().lower() for item in value]


class CreateReportResponse(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str
    pdf_url: str
    json_url: str
    dashboard_url: str
    validation_url: str
    evidence_url: str
    metrics_url: str
    intelligence_url: str


class ReportUsageMetrics(BaseModel):
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


class ReportJobMetrics(BaseModel):
    """Generic per-job LLM usage and cost estimate for any consuming application."""

    version: str = Field(default="report-metrics-v1")
    duration_sec: float | None = None
    llm_provider: str | None = None
    models_configured: dict[str, str | None] | None = None
    selected_analysts: list[str] = Field(default_factory=list)
    usage: ReportUsageMetrics | None = None
    estimated_cost_usd: float | None = None
    by_model: dict[str, Any] | None = None
    cost_estimation: dict[str, Any] | None = None


class ReportJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    ticker: str
    analysis_date: str
    decision: Any | None = None
    error: str | None = None
    markdown_path: str | None = None
    pdf_path: str | None = None
    pdf_url: str | None = None
    json_url: str | None = None
    dashboard_url: str | None = None
    validation_url: str | None = None
    evidence_url: str | None = None
    metrics_url: str | None = None
    intelligence_url: str | None = None
    metrics: ReportJobMetrics | None = None


class ReportValidationLiteRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = Field(..., min_length=1, max_length=32)
    strategy: str | None = None
    rawSignal: str | None = None
    finalSignal: str | None = None
    tradeAllowed: bool | None = None
    confidenceScore: int | None = None
    confidenceGrade: str | None = None
    topBlockers: list[str] = Field(default_factory=list)
    watchlistConditions: list[Any] = Field(default_factory=list)
    supplyChainContext: dict[str, Any] | None = None


class JobRecord:
    def __init__(
        self,
        job_id: str,
        request: ReportRequest,
        trace: dict[str, Any] | None = None,
    ) -> None:
        self.job_id = job_id
        self.request = request
        self.trace = trace or current_trace()
        self.status = JobStatus.queued
        self.result: ReportResult | None = None
        self.error: str | None = None
        self.future: Future[ReportResult] | None = None
        self.created_at = datetime.now()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None


executor = ThreadPoolExecutor(max_workers=int(os.getenv("TRADINGAGENTS_SERVICE_WORKERS", "1")))
jobs: dict[str, JobRecord] = {}


def _resume_interrupted_jobs_enabled() -> bool:
    raw = os.getenv("TRADINGAGENTS_JOB_RESUME_INTERRUPTED", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _iter_persisted_job_ids() -> list[str]:
    store = _job_store_dir()
    if not store.exists():
        return []
    return sorted(path.stem for path in store.glob("*.json") if path.is_file())


def recover_jobs_from_disk() -> dict[str, int]:
    """Reload persisted jobs after a process restart.

    - completed / failed: restore into memory for polling/downloads
    - queued: re-submit to the worker pool
    - running: mark failed (interrupted) unless TRADINGAGENTS_JOB_RESUME_INTERRUPTED=1
    """
    stats = {
        "loaded": 0,
        "requeued": 0,
        "interrupted_failed": 0,
        "interrupted_resumed": 0,
        "skipped": 0,
    }
    resume_interrupted = _resume_interrupted_jobs_enabled()

    for job_id in _iter_persisted_job_ids():
        if job_id in jobs:
            stats["skipped"] += 1
            continue
        record = _load_job_record(job_id)
        if record is None:
            stats["skipped"] += 1
            continue

        jobs[job_id] = record
        stats["loaded"] += 1

        if record.status == JobStatus.queued:
            record.future = executor.submit(_run_job_in_context, record)
            stats["requeued"] += 1
            log_info("report_job_requeued_after_restart", jobId=job_id)
        elif record.status == JobStatus.running:
            if resume_interrupted:
                record.status = JobStatus.queued
                record.started_at = None
                record.error = None
                _write_job_record(record)
                record.future = executor.submit(_run_job_in_context, record)
                stats["interrupted_resumed"] += 1
                log_info("report_job_resumed_after_restart", jobId=job_id)
            else:
                record.status = JobStatus.failed
                record.error = (
                    "Job interrupted by service restart. "
                    "Re-submit the report request, or set "
                    "TRADINGAGENTS_JOB_RESUME_INTERRUPTED=1 to auto-retry."
                )
                record.completed_at = datetime.now()
                _write_job_record(record)
                stats["interrupted_failed"] += 1
                log_warning("report_job_interrupted_by_restart", jobId=job_id)

    if stats["loaded"]:
        log_info("job_store_recovered", **stats)
    return stats


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    recover_jobs_from_disk()
    yield


app = FastAPI(
    title="Vein Reports Service API",
    version="0.1.0",
    description="Run Vein Reports analysis jobs and download generated PDF reports.",
    lifespan=_lifespan,
)
app.add_middleware(TraceMiddleware)


def _error_body(
    *,
    status_code: int,
    message: str,
    path: str,
    error: str | None = None,
) -> dict[str, Any]:
    trace = current_trace()
    body: dict[str, Any] = {
        "statusCode": status_code,
        "message": message,
        "requestId": trace.get("requestId"),
        "correlationId": trace.get("correlationId"),
        "timestamp": datetime.now().isoformat(),
        "path": path,
    }
    if error:
        body["error"] = error
    return body


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    if exc.status_code >= 500:
        log_exception(
            "http_request_failed",
            exc,
            method=request.method,
            path=request.url.path,
            status=exc.status_code,
        )
    else:
        log_warning(
            "http_request_rejected",
            method=request.method,
            path=request.url.path,
            status=exc.status_code,
            message=detail,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(status_code=exc.status_code, message=detail, path=request.url.path),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_exception(
        "http_request_failed",
        exc,
        method=request.method,
        path=request.url.path,
        status=500,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            status_code=500,
            message="Internal server error",
            path=request.url.path,
            error="Internal Server Error",
        ),
    )


def _reports_root() -> Path:
    return Path(os.getenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", "reports/api")).resolve()


def _job_store_dir() -> Path:
    return _reports_root() / "_jobs"


def _job_store_path(job_id: str) -> Path:
    return _job_store_dir() / f"{job_id}.json"


def _write_job_record(record: JobRecord) -> None:
    _job_store_dir().mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "job_id": record.job_id,
        "status": record.status.value,
        "request": asdict(record.request),
        "error": record.error,
        "trace": record.trace,
        "created_at": _dt_or_none(record.created_at),
        "started_at": _dt_or_none(record.started_at),
        "completed_at": _dt_or_none(record.completed_at),
        "result": _result_payload(record.result),
    }
    path = _job_store_path(record.job_id)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp_path.replace(path)


def _load_job_record(job_id: str) -> JobRecord | None:
    path = _job_store_path(job_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        request = ReportRequest(**payload["request"])
        record = JobRecord(job_id=payload["job_id"], request=request, trace=payload.get("trace"))
        record.status = JobStatus(payload["status"])
        record.error = payload.get("error")
        record.created_at = _parse_dt(payload.get("created_at")) or datetime.now()
        record.started_at = _parse_dt(payload.get("started_at"))
        record.completed_at = _parse_dt(payload.get("completed_at"))
        record.result = _load_result(payload.get("result"))
        return record
    except Exception as exc:
        log_exception("job_metadata_load_failed", exc, jobId=job_id)
        return None


def _result_payload(result: ReportResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "job_id": result.job_id,
        "ticker": result.ticker,
        "analysis_date": result.analysis_date,
        "decision": result.decision,
        "report_dir": str(result.report_dir),
        "markdown_path": str(result.markdown_path),
        "pdf_path": str(result.pdf_path),
        "metrics": result.metrics,
    }


def _load_result(payload: dict[str, Any] | None) -> ReportResult | None:
    if not payload:
        return None
    return ReportResult(
        job_id=payload["job_id"],
        ticker=payload["ticker"],
        analysis_date=payload["analysis_date"],
        decision=payload.get("decision"),
        report_dir=Path(payload["report_dir"]),
        markdown_path=Path(payload["markdown_path"]),
        pdf_path=Path(payload["pdf_path"]),
        metrics=payload.get("metrics"),
    )


def _resolve_job_metrics(record: JobRecord) -> dict[str, Any] | None:
    if record.result and record.result.metrics:
        return record.result.metrics
    if record.result is None:
        return None
    from tradingagents.metrics.report_metrics import read_report_metrics

    return read_report_metrics(record.result.report_dir)


def _metrics_response(record: JobRecord) -> ReportJobMetrics | None:
    raw = _resolve_job_metrics(record)
    if not raw:
        return None
    usage = raw.get("usage") or {}
    return ReportJobMetrics(
        version=raw.get("version", "report-metrics-v1"),
        duration_sec=raw.get("duration_sec"),
        llm_provider=raw.get("llm_provider"),
        models_configured=raw.get("models_configured"),
        selected_analysts=raw.get("selected_analysts") or [],
        usage=ReportUsageMetrics(**usage) if usage else None,
        estimated_cost_usd=raw.get("estimated_cost_usd"),
        by_model=raw.get("by_model"),
        cost_estimation=raw.get("cost_estimation"),
    )


def _dt_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def require_service_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("TRADINGAGENTS_SERVICE_API_KEY")
    env = (
        os.getenv("TRADINGAGENTS_ENV")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("NODE_ENV")
        or os.getenv("ENV")
        or ""
    ).strip().lower()
    production = env in {"production", "prod"}
    if not expected:
        if production:
            log_warning("service_auth_misconfigured", reason="missing_api_key_in_production")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="TRADINGAGENTS_SERVICE_API_KEY is required in production",
            )
        return
    if x_api_key != expected:
        log_warning("service_auth_failed", reason="invalid_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service API key",
        )


def _request_subject(request: ReportRequest) -> str:
    return resolve_report_subject(
        ticker=request.ticker,
        target=request.intelligence_target,
    )


def _run_job_in_context(record: JobRecord) -> ReportResult:
    tokens = bind_trace_from_mapping(record.trace, default_service="vein-reports")
    job_tokens = bind_trace(job_id=record.job_id, span="report.job.execute")
    try:
        return _execute_job(record)
    finally:
        reset_trace(job_tokens)
        reset_trace(tokens)


def _execute_job(record: JobRecord) -> ReportResult:
    record.status = JobStatus.running
    record.started_at = datetime.now()
    _write_job_record(record)

    log_info(
        "report_job_started",
        jobId=record.job_id,
        ticker=_request_subject(record.request),
        analysisDate=record.request.analysis_date,
        analysts=list(record.request.selected_analysts),
        llmProvider=record.request.llm_provider or "default",
    )

    try:
        record.result = run_report_job(record.request, job_id=record.job_id)
        record.status = JobStatus.completed
        record.completed_at = datetime.now()
        _write_job_record(record)
        duration = (record.completed_at - record.started_at).total_seconds()

        log_info(
            "report_job_completed",
            jobId=record.job_id,
            durationSec=round(duration, 2),
            decision=record.result.decision,
            llmCalls=(record.result.metrics or {}).get("usage", {}).get("llm_calls"),
            toolCalls=(record.result.metrics or {}).get("usage", {}).get("tool_calls"),
            tokensIn=(record.result.metrics or {}).get("usage", {}).get("tokens_in"),
            tokensOut=(record.result.metrics or {}).get("usage", {}).get("tokens_out"),
            estimatedCostUsd=(record.result.metrics or {}).get("estimated_cost_usd"),
        )
        return record.result
    except Exception as exc:
        record.error = str(exc)
        record.status = JobStatus.failed
        record.completed_at = datetime.now()
        duration = (record.completed_at - record.started_at).total_seconds()

        if "insufficient_quota" in record.error:
            user_friendly_error = "Service temporarily unavailable due to API quota limits. Please try again later or contact support."
            log_error(
                "report_job_failed_quota",
                jobId=record.job_id,
                durationSec=round(duration, 2),
            )
            record.error = user_friendly_error
        else:
            log_exception(
                "report_job_failed",
                exc,
                jobId=record.job_id,
                durationSec=round(duration, 2),
            )
        _write_job_record(record)
        raise


def _get_job(job_id: str) -> JobRecord:
    record = jobs.get(job_id)
    if record is None:
        record = _load_job_record(job_id)
        if record is not None:
            jobs[job_id] = record
    if record is None:
        log_warning("job_not_found", jobId=job_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return record


def _report_url(job_id: str, suffix: str) -> str:
    return f"/v1/reports/{job_id}/{suffix}"


def _read_completed_artifact(job_id: str, filename: str) -> dict[str, Any]:
    record = _get_job(job_id)
    if record.status != JobStatus.completed or record.result is None:
        log_warning(
            "artifact_download_incomplete",
            jobId=job_id,
            status=record.status.value,
            filename=filename,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job is {record.status}",
        )

    artifact_path = Path(record.result.report_dir) / filename
    if not artifact_path.exists():
        log_error("artifact_not_found", jobId=job_id, filename=filename, path=str(artifact_path))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{filename} not found",
        )

    try:
        return json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log_exception("artifact_read_failed", exc, jobId=job_id, filename=filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to read {filename}",
        ) from exc


@app.get("/health")
def health() -> dict[str, str]:
    active_jobs = sum(1 for j in jobs.values() if j.status == JobStatus.running)
    return {"status": "ok", "active_jobs": str(active_jobs), "total_jobs": str(len(jobs))}


def _ping(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"ok": True, "statusCode": getattr(response, "status", 200)}
    except Exception as exc:  # noqa: BLE001 — readiness must never raise
        return {"ok": False, "error": str(exc), "errorType": exc.__class__.__name__}


@app.get("/ready")
def ready() -> dict[str, Any]:
    """Readiness: local process plus optional sibling reachability when integrations are enabled."""
    from tradingagents.integrations.golden_trend_client import is_golden_trend_enabled
    from tradingagents.integrations.vein_aggregator_client import is_vein_aggregator_enabled
    from tradingagents.integrations.vein_explorer_client import is_vein_pull_enabled

    integrations: dict[str, Any] = {
        "signals": {"enabled": is_golden_trend_enabled()},
        "explorer": {"enabled": is_vein_pull_enabled()},
        "aggregator": {"enabled": is_vein_aggregator_enabled()},
        "authConfigured": bool(os.getenv("TRADINGAGENTS_SERVICE_API_KEY")),
    }

    if is_golden_trend_enabled():
        base = os.getenv("TRADINGAGENTS_GOLDEN_TREND_BASE_URL", "").strip().rstrip("/")
        integrations["signals"]["baseUrl"] = base or None
        integrations["signals"]["reachable"] = _ping(f"{base}/api/health")["ok"] if base else False

    if is_vein_pull_enabled():
        base = os.getenv("TRADINGAGENTS_VEIN_EXPLORER_BASE_URL", "").strip().rstrip("/")
        integrations["explorer"]["baseUrl"] = base or None
        integrations["explorer"]["reachable"] = _ping(f"{base}/v1/health")["ok"] if base else False

    if is_vein_aggregator_enabled():
        base = os.getenv("TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL", "").strip().rstrip("/")
        integrations["aggregator"]["baseUrl"] = base or None
        integrations["aggregator"]["reachable"] = _ping(f"{base}/health")["ok"] if base else False

    ready_ok = True
    for name in ("signals", "explorer", "aggregator"):
        entry = integrations[name]
        if entry.get("enabled") and entry.get("reachable") is False:
            ready_ok = False

    env = (
        os.getenv("TRADINGAGENTS_ENV")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("NODE_ENV")
        or os.getenv("ENV")
        or ""
    ).strip().lower()
    if env in {"production", "prod"} and not integrations["authConfigured"]:
        ready_ok = False

    return {
        "status": "ready" if ready_ok else "degraded",
        "ready": ready_ok,
        "integrations": integrations,
    }


@app.post(
    "/v1/reports",
    response_model=CreateReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_key)],
)
def create_report(payload: CreateReportRequest) -> CreateReportResponse:
    analysis_date = payload.analysis_date or datetime.now().strftime("%Y-%m-%d")
    job_id = uuid4().hex
    intelligence_target = payload.target.to_target() if payload.target else None
    subject = resolve_report_subject(ticker=payload.ticker, target=intelligence_target)
    context_bundle = (
        payload.context_bundle.model_dump(mode="json")
        if payload.context_bundle is not None
        else None
    )

    # Apply tier-based configurations
    selected_analysts = list(payload.selected_analysts)
    max_debate_rounds = payload.max_debate_rounds
    max_risk_discuss_rounds = payload.max_risk_discuss_rounds

    if payload.report_tier == ReportTier.free:
        # Free tier: minimal configuration for faster processing
        selected_analysts = ["market"]  # Only market analyst for free tier
        max_debate_rounds = max_debate_rounds or 1  # Limit debate rounds
        max_risk_discuss_rounds = max_risk_discuss_rounds or 1  # Limit risk discussion
        log_info(
            "report_job_create_free_tier",
            jobId=job_id,
            ticker=subject,
            analysisDate=analysis_date,
            analysts=selected_analysts,
        )
    else:
        if context_bundle is not None and "supply_chain" not in selected_analysts:
            selected_analysts.append("supply_chain")
        log_info(
            "report_job_create_pro_tier",
            jobId=job_id,
            ticker=subject,
            analysisDate=analysis_date,
            analysts=selected_analysts,
        )

    request = ReportRequest(
        ticker=payload.ticker,
        analysis_date=analysis_date,
        intelligence_target=intelligence_target,
        selected_analysts=tuple(selected_analysts),
        llm_provider=payload.llm_provider,
        deep_think_llm=payload.deep_think_llm,
        quick_think_llm=payload.quick_think_llm,
        backend_url=payload.backend_url,
        output_language=payload.output_language,
        max_debate_rounds=max_debate_rounds,
        max_risk_discuss_rounds=max_risk_discuss_rounds,
        checkpoint_enabled=payload.checkpoint_enabled,
        user_id=payload.user_id,
        context_bundle=context_bundle,
        strategy_id=payload.strategy_id,
        report_tier=payload.report_tier.value,
        full_report=payload.full_report,
    )
    try:
        validate_report_request(request)
    except ValueError as exc:
        log_warning("report_job_validation_failed", jobId=job_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    record = JobRecord(job_id, request, trace=current_trace())
    jobs[job_id] = record
    _write_job_record(record)
    record.future = executor.submit(_run_job_in_context, record)

    log_info("report_job_queued", jobId=job_id, ticker=subject, reportTier=payload.report_tier.value)

    return CreateReportResponse(
        job_id=job_id,
        status=record.status,
        status_url=f"/v1/reports/{job_id}",
        pdf_url=_report_url(job_id, "pdf"),
        json_url=_report_url(job_id, "json"),
        dashboard_url=_report_url(job_id, "dashboard"),
        validation_url=_report_url(job_id, "validation"),
        evidence_url=_report_url(job_id, "evidence"),
        metrics_url=_report_url(job_id, "metrics"),
        intelligence_url=_report_url(job_id, "intelligence"),
    )


@app.get(
    "/v1/reports/{job_id}",
    response_model=ReportJobResponse,
    dependencies=[Depends(require_service_key)],
)
def get_report(job_id: str) -> ReportJobResponse:
    record = _get_job(job_id)
    result = record.result
    metrics = _metrics_response(record) if result else None

    return ReportJobResponse(
        job_id=record.job_id,
        status=record.status,
        ticker=result.ticker if result else _request_subject(record.request),
        analysis_date=record.request.analysis_date,
        decision=result.decision if result else None,
        error=record.error,
        markdown_path=str(result.markdown_path) if result else None,
        pdf_path=str(result.pdf_path) if result else None,
        pdf_url=_report_url(job_id, "pdf") if result else None,
        json_url=_report_url(job_id, "json") if result else None,
        dashboard_url=_report_url(job_id, "dashboard") if result else None,
        validation_url=_report_url(job_id, "validation") if result else None,
        evidence_url=_report_url(job_id, "evidence") if result else None,
        metrics_url=_report_url(job_id, "metrics") if result else None,
        intelligence_url=_report_url(job_id, "intelligence") if result else None,
        metrics=metrics,
    )


@app.get("/v1/reports/{job_id}/json", dependencies=[Depends(require_service_key)])
def download_report_json(job_id: str) -> dict:
    """Download the complete report data as JSON for dashboard integration."""
    record = _get_job(job_id)
    if record.status != JobStatus.completed or record.result is None:
        log_warning(
            "json_download_incomplete",
            jobId=job_id,
            status=record.status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job not completed or no results available",
        )

    # Read the JSON log file that contains all the report data
    # The JSON logs are saved in: reports/api/_logs/job_id / ticker / "TradingAgentsStrategy_logs"
    # But record.result.report_dir is: reports/api/job_id
    # So we need to go to: reports/api/_logs/job_id / ticker / "TradingAgentsStrategy_logs"
    log_dir = record.result.report_dir.parent / "_logs" / job_id / record.result.ticker / "TradingAgentsStrategy_logs"
    log_files = list(log_dir.glob("full_states_log_*.json"))

    if not log_files:
        log_error("json_log_not_found", jobId=job_id, logDir=str(log_dir))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report data not found",
        )

    # Get the most recent log file
    log_file = sorted(log_files, key=lambda x: x.stat().st_mtime)[-1]

    try:
        with open(log_file, encoding="utf-8") as f:
            report_data = json.load(f)
        return report_data
    except Exception as exc:
        log_exception("json_report_read_failed", exc, jobId=job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read report data",
        ) from exc


@app.get(
    "/v1/reports/{job_id}/metrics",
    dependencies=[Depends(require_service_key)],
    summary="Download per-job LLM usage and cost estimate",
)
def download_report_metrics(job_id: str) -> dict[str, Any]:
    """Return cost_metrics.json — generic usage metrics for any consuming application."""
    return _read_completed_artifact(job_id, "cost_metrics.json")


@app.get(
    "/v1/reports/{job_id}/dashboard",
    dependencies=[Depends(require_service_key)],
    summary="Download the canonical report dashboard artifact",
)
def download_report_dashboard(job_id: str) -> dict[str, Any]:
    """Return dashboard.json, the machine-readable public recommendation summary."""
    return _read_completed_artifact(job_id, "dashboard.json")


@app.get(
    "/v1/reports/{job_id}/validation",
    dependencies=[Depends(require_service_key)],
    summary="Download the validation report artifact",
)
def download_validation_report(job_id: str) -> dict[str, Any]:
    """Return validation_report.json with blocking issues, metadata, and evidence status."""
    return _read_completed_artifact(job_id, "validation_report.json")


@app.get(
    "/v1/reports/{job_id}/evidence",
    dependencies=[Depends(require_service_key)],
    summary="Download the decision evidence bundle",
)
def download_decision_evidence(job_id: str) -> dict[str, Any]:
    """Return decision_evidence_bundle.json for downstream audit and dashboard ingestion."""
    return _read_completed_artifact(job_id, "decision_evidence_bundle.json")


@app.get(
    "/v1/reports/{job_id}/intelligence",
    dependencies=[Depends(require_service_key)],
    summary="Download Vein Aggregator intelligence provenance",
)
def download_intelligence_bundle(job_id: str) -> dict[str, Any]:
    """Return intelligence_bundle.json with retrieval status and briefs when Aggregator was used."""
    return _read_completed_artifact(job_id, "intelligence_bundle.json")


@app.get("/v1/reports/{job_id}/pdf", dependencies=[Depends(require_service_key)])
def download_report_pdf(job_id: str) -> FileResponse:
    record = _get_job(job_id)
    if record.status != JobStatus.completed or record.result is None:
        log_warning(
            "pdf_download_incomplete",
            jobId=job_id,
            status=record.status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job is {record.status}",
        )

    pdf_path = Path(record.result.pdf_path)
    if not pdf_path.exists():
        log_error("pdf_not_found", jobId=job_id, path=str(pdf_path))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pdf not found",
        )

    log_info("pdf_download", jobId=job_id, filename=pdf_path.name)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )


@app.post(
    "/v1/report-validation-lite",
    dependencies=[Depends(require_service_key)],
    summary="Lightweight signal/report fusion validation for Vein Signals",
)
def report_validation_lite(payload: ReportValidationLiteRequest) -> dict[str, Any]:
    from tradingagents.validation.report_validation_lite import validate_report_lite

    body = payload.model_dump(exclude_none=True)
    body["symbol"] = payload.symbol.strip().upper()
    return validate_report_lite(body)

