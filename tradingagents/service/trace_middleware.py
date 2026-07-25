"""FastAPI middleware for request/correlation IDs and structured request logs."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from tradingagents.service.trace_logging import (
    bind_trace,
    job_id_from_request_path,
    log_exception,
    log_info,
    reset_trace,
)


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        correlation_id = request.headers.get("x-correlation-id") or request_id
        path = request.url.path
        method = request.method
        tokens = bind_trace(
            request_id=request_id,
            correlation_id=correlation_id,
            service="vein-reports",
            span=f"http.{method}.{path}",
            job_id=job_id_from_request_path(path),
        )
        started = time.perf_counter()
        log_info("http_request_started", method=method, path=path)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            response.headers["x-correlation-id"] = correlation_id
            log_info(
                "http_request_completed",
                method=method,
                path=path,
                statusCode=response.status_code,
                durationMs=round((time.perf_counter() - started) * 1000, 2),
            )
            return response
        except Exception as exc:
            log_exception(
                "http_request_failed",
                exc,
                method=method,
                path=path,
                durationMs=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            reset_trace(tokens)
