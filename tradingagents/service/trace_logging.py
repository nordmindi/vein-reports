"""Structured trace logging for Vein Reports (wraps shared vein_trace_core)."""

from __future__ import annotations

import re

from . import vein_trace_core as _core
from .vein_trace_core import (  # noqa: F401 — re-export platform API
    bind_trace,
    bind_trace_from_mapping,
    current_trace,
    log_error,
    log_event,
    log_exception,
    log_info,
    log_warning,
    reset_trace,
    trace_headers,
    trace_scope,
)

_REPORT_JOB_PATH_RE = re.compile(r"^/v1/reports/([^/]+)")

_core.DEFAULT_SERVICE = "vein-reports"


def job_id_from_request_path(path: str) -> str | None:
    """Extract a report job id from `/v1/reports/{job_id}` and sub-resource paths."""
    match = _REPORT_JOB_PATH_RE.match(path)
    if not match:
        return None
    return _core._optional_str(match.group(1))
