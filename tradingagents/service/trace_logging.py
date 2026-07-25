"""Structured trace logging with correlation IDs for Vein Reports."""

from __future__ import annotations

import json
import re
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Iterator

_REPORT_JOB_PATH_RE = re.compile(r"^/v1/reports/([^/]+)")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_service: ContextVar[str | None] = ContextVar("service", default=None)
_span: ContextVar[str | None] = ContextVar("span", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)


def bind_trace(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    service: str | None = None,
    span: str | None = None,
    job_id: str | None = None,
) -> dict[str, Token[Any]]:
    tokens: dict[str, Token[Any]] = {}
    if request_id is not None:
        tokens["request_id"] = _request_id.set(request_id)
    if correlation_id is not None:
        tokens["correlation_id"] = _correlation_id.set(correlation_id)
    if service is not None:
        tokens["service"] = _service.set(service)
    if span is not None:
        tokens["span"] = _span.set(span)
    if job_id is not None:
        tokens["job_id"] = _job_id.set(job_id)
    return tokens


def reset_trace(tokens: dict[str, Token[Any]]) -> None:
    for name, token in tokens.items():
        if name == "request_id":
            _request_id.reset(token)
        elif name == "correlation_id":
            _correlation_id.reset(token)
        elif name == "service":
            _service.reset(token)
        elif name == "span":
            _span.reset(token)
        elif name == "job_id":
            _job_id.reset(token)


def bind_trace_from_mapping(trace: dict[str, Any] | None, *, default_service: str) -> dict[str, Token[Any]]:
    mapping = trace if isinstance(trace, dict) else {}
    return bind_trace(
        request_id=_optional_str(mapping.get("requestId") or mapping.get("request_id")),
        correlation_id=_optional_str(mapping.get("correlationId") or mapping.get("correlation_id")),
        service=_optional_str(mapping.get("service")) or default_service,
        span=_optional_str(mapping.get("span")),
        job_id=_optional_str(mapping.get("jobId") or mapping.get("job_id")),
    )


@contextmanager
def trace_scope(**kwargs: Any) -> Iterator[None]:
    tokens = bind_trace(**kwargs)
    try:
        yield
    finally:
        reset_trace(tokens)


def current_trace() -> dict[str, str | None]:
    return {
        "requestId": _request_id.get(),
        "correlationId": _correlation_id.get(),
        "service": _service.get(),
        "span": _span.get(),
        "jobId": _job_id.get(),
    }


def trace_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    request_id = _request_id.get()
    correlation_id = _correlation_id.get()
    if request_id:
        headers["x-request-id"] = request_id
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    return headers


def log_event(level: str, event: str, **fields: Any) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.lower(),
        "event": event,
        "service": _service.get() or fields.pop("service", None) or "vein-reports",
        "requestId": _request_id.get(),
        "correlationId": _correlation_id.get(),
        "jobId": _job_id.get(),
        "span": _span.get(),
        **fields,
    }
    print(json.dumps(record, default=str), file=sys.stderr, flush=True)


def log_info(event: str, **fields: Any) -> None:
    log_event("info", event, **fields)


def log_warning(event: str, **fields: Any) -> None:
    log_event("warning", event, **fields)


def log_error(event: str, **fields: Any) -> None:
    log_event("error", event, **fields)


def log_exception(event: str, exc: BaseException, **fields: Any) -> None:
    log_error(
        event,
        error=str(exc),
        errorType=exc.__class__.__name__,
        traceback=traceback.format_exc(limit=8),
        **fields,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def job_id_from_request_path(path: str) -> str | None:
    """Extract a report job id from `/v1/reports/{job_id}` and sub-resource paths."""
    match = _REPORT_JOB_PATH_RE.match(path)
    if not match:
        return None
    return _optional_str(match.group(1))
