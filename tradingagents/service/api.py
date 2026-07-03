from __future__ import annotations

import json
import logging
import os
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from tradingagents.service.runner import (
    ReportRequest,
    ReportResult,
    run_report_job,
    validate_report_request,
)

# Load environment variables
load_dotenv()
load_dotenv(".env.enterprise", override=False)

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReportTier(str, Enum):
    free = "free"
    pro = "pro"


class CreateReportRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    analysis_date: str | None = None
    selected_analysts: list[str] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals"]
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
    report_tier: ReportTier = ReportTier.pro  # Default to pro for backward compatibility
    context_bundle: dict[str, Any] | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("selected_analysts")
    @classmethod
    def normalize_analysts(cls, value: list[str]) -> list[str]:
        return [item.strip().lower() for item in value]


class CreateReportResponse(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str
    pdf_url: str


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


class JobRecord:
    def __init__(self, job_id: str, request: ReportRequest) -> None:
        self.job_id = job_id
        self.request = request
        self.status = JobStatus.queued
        self.result: ReportResult | None = None
        self.error: str | None = None
        self.future: Future[ReportResult] | None = None
        self.created_at = datetime.now()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None


app = FastAPI(
    title="TradingAgents Service API",
    version="0.1.0",
    description="Run TradingAgents analysis jobs and download generated PDF reports.",
)

executor = ThreadPoolExecutor(max_workers=int(os.getenv("TRADINGAGENTS_SERVICE_WORKERS", "1")))
jobs: dict[str, JobRecord] = {}


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
        record = JobRecord(job_id=payload["job_id"], request=request)
        record.status = JobStatus(payload["status"])
        record.error = payload.get("error")
        record.created_at = _parse_dt(payload.get("created_at")) or datetime.now()
        record.started_at = _parse_dt(payload.get("started_at"))
        record.completed_at = _parse_dt(payload.get("completed_at"))
        record.result = _load_result(payload.get("result"))
        return record
    except Exception as exc:
        logger.error("Failed to load job metadata for %s: %s", job_id, exc, exc_info=True)
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
    if expected and x_api_key != expected:
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service API key",
        )


def _execute_job(record: JobRecord) -> ReportResult:
    record.status = JobStatus.running
    record.started_at = datetime.now()
    _write_job_record(record)
    
    logger.info(
        f"Job {record.job_id} started | Ticker: {record.request.ticker} | "
        f"Date: {record.request.analysis_date} | Analysts: {record.request.selected_analysts} | "
        f"LLM: {record.request.llm_provider or 'default'}"
    )
    
    try:
        record.result = run_report_job(record.request, job_id=record.job_id)
        record.status = JobStatus.completed
        record.completed_at = datetime.now()
        _write_job_record(record)
        duration = (record.completed_at - record.started_at).total_seconds()
        
        logger.info(
            f"Job {record.job_id} completed successfully | "
            f"Duration: {duration:.2f}s | Decision: {record.result.decision}"
        )
        return record.result
    except Exception as exc:
        record.error = str(exc)
        record.status = JobStatus.failed
        record.completed_at = datetime.now()
        duration = (record.completed_at - record.started_at).total_seconds()
        
        # Check if this is a quota error from OpenAI
        if "insufficient_quota" in record.error:
            user_friendly_error = "Service temporarily unavailable due to API quota limits. Please try again later or contact support."
            logger.error(
                f"Job {record.job_id} failed due to API quota limits | Duration: {duration:.2f}s"
            )
            # Log the full error with stack trace only for debugging
            logger.debug(
                f"Quota error details: {record.error}",
                exc_info=True,
            )
            # Update the error message that will be returned to the user
            record.error = user_friendly_error
        else:
            logger.error(
                f"Job {record.job_id} failed | Duration: {duration:.2f}s | "
                f"Error: {record.error}",
                exc_info=True,
            )
        _write_job_record(record)
        raise


def _get_job(job_id: str) -> JobRecord:
    record = jobs.get(job_id)
    if record is None:
        record = _load_job_record(job_id)
    if record is None:
        logger.warning(f"Job {job_id} not found in memory or persisted job store")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return record


@app.get("/health")
def health() -> dict[str, str]:
    active_jobs = sum(1 for j in jobs.values() if j.status == JobStatus.running)
    logger.debug(f"Health check | Active jobs: {active_jobs} | Total jobs: {len(jobs)}")
    return {"status": "ok", "active_jobs": str(active_jobs), "total_jobs": str(len(jobs))}


@app.post(
    "/v1/reports",
    response_model=CreateReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_key)],
)
def create_report(payload: CreateReportRequest) -> CreateReportResponse:
    analysis_date = payload.analysis_date or datetime.now().strftime("%Y-%m-%d")
    job_id = uuid4().hex
    
    # Apply tier-based configurations
    selected_analysts = list(payload.selected_analysts)
    max_debate_rounds = payload.max_debate_rounds
    max_risk_discuss_rounds = payload.max_risk_discuss_rounds
    
    if payload.report_tier == ReportTier.free:
        # Free tier: minimal configuration for faster processing
        selected_analysts = ["market"]  # Only market analyst for free tier
        max_debate_rounds = max_debate_rounds or 1  # Limit debate rounds
        max_risk_discuss_rounds = max_risk_discuss_rounds or 1  # Limit risk discussion
        logger.info(
            f"Creating FREE TIER job {job_id} | Ticker: {payload.ticker} | "
            f"Date: {analysis_date} | Analysts: {selected_analysts}"
        )
    else:
        if payload.context_bundle is not None and "supply_chain" not in selected_analysts:
            selected_analysts.append("supply_chain")
        # Pro tier: full configuration
        logger.info(
            f"Creating PRO TIER job {job_id} | Ticker: {payload.ticker} | "
            f"Date: {analysis_date} | Analysts: {selected_analysts}"
        )
    
    request = ReportRequest(
        ticker=payload.ticker,
        analysis_date=analysis_date,
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
        context_bundle=payload.context_bundle,
    )
    try:
        validate_report_request(request)
    except ValueError as exc:
        logger.error(f"Job {job_id} validation failed: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    record = JobRecord(job_id, request)
    jobs[job_id] = record
    _write_job_record(record)
    record.future = executor.submit(_execute_job, record)
    
    logger.info(f"Job {job_id} queued successfully")

    return CreateReportResponse(
        job_id=job_id,
        status=record.status,
        status_url=f"/v1/reports/{job_id}",
        pdf_url=f"/v1/reports/{job_id}/pdf",
    )


@app.get(
    "/v1/reports/{job_id}",
    response_model=ReportJobResponse,
    dependencies=[Depends(require_service_key)],
)
def get_report(job_id: str) -> ReportJobResponse:
    record = _get_job(job_id)
    result = record.result
    
    logger.debug(f"Fetching job status | Job: {job_id} | Status: {record.status}")
    
    return ReportJobResponse(
        job_id=record.job_id,
        status=record.status,
        ticker=record.request.ticker,
        analysis_date=record.request.analysis_date,
        decision=result.decision if result else None,
        error=record.error,
        markdown_path=str(result.markdown_path) if result else None,
        pdf_path=str(result.pdf_path) if result else None,
        pdf_url=f"/v1/reports/{job_id}/pdf" if result else None,
        json_url=f"/v1/reports/{job_id}/json" if result else None,
    )


@app.get("/v1/reports/{job_id}/json", dependencies=[Depends(require_service_key)])
def download_report_json(job_id: str) -> dict:
    """Download the complete report data as JSON for dashboard integration."""
    record = _get_job(job_id)
    if record.status != JobStatus.completed or record.result is None:
        logger.warning(
            f"JSON download attempted for incomplete job | Job: {job_id} | Status: {record.status}"
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
    log_files = list(log_dir.glob(f"full_states_log_*.json"))
    
    if not log_files:
        logger.error(f"JSON log file not found for job {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report data not found",
        )
    
    # Get the most recent log file
    log_file = sorted(log_files, key=lambda x: x.stat().st_mtime)[-1]
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            report_data = json.load(f)
        return report_data
    except Exception as e:
        logger.error(f"Failed to read JSON report for job {job_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read report data",
        )


@app.get("/v1/reports/{job_id}/pdf", dependencies=[Depends(require_service_key)])
def download_report_pdf(job_id: str) -> FileResponse:
    record = _get_job(job_id)
    if record.status != JobStatus.completed or record.result is None:
        logger.warning(
            f"PDF download attempted for incomplete job | Job: {job_id} | Status: {record.status}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job is {record.status}",
        )

    pdf_path = Path(record.result.pdf_path)
    if not pdf_path.exists():
        logger.error(f"PDF file not found | Job: {job_id} | Path: {pdf_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pdf not found",
        )

    logger.info(f"Downloading PDF | Job: {job_id} | File: {pdf_path.name}")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )

