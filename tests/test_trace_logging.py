import io
import json
import sys
import unittest

from tradingagents.service.trace_logging import (
    bind_trace,
    bind_trace_from_mapping,
    current_trace,
    job_id_from_request_path,
    log_event,
    reset_trace,
    trace_headers,
)


class TraceLoggingTests(unittest.TestCase):
    def test_bind_and_current_trace(self):
        tokens = bind_trace(
            request_id="req-1",
            correlation_id="corr-1",
            service="vein-reports",
            span="test.span",
            job_id="job-1",
        )
        try:
            trace = current_trace()
            self.assertEqual(trace["requestId"], "req-1")
            self.assertEqual(trace["correlationId"], "corr-1")
            self.assertEqual(trace["service"], "vein-reports")
            self.assertEqual(trace["jobId"], "job-1")
        finally:
            reset_trace(tokens)

    def test_bind_trace_from_mapping(self):
        tokens = bind_trace_from_mapping(
            {"requestId": "req-2", "correlationId": "corr-2", "jobId": "job-2"},
            default_service="vein-reports",
        )
        try:
            self.assertEqual(trace_headers(), {"x-request-id": "req-2", "x-correlation-id": "corr-2"})
        finally:
            reset_trace(tokens)

    def test_job_id_from_request_path(self):
        self.assertEqual(
            job_id_from_request_path("/v1/reports/1ee5ada9ce7a4790a7c219dbeca61f85"),
            "1ee5ada9ce7a4790a7c219dbeca61f85",
        )
        self.assertEqual(
            job_id_from_request_path("/v1/reports/abc123/pdf"),
            "abc123",
        )
        self.assertIsNone(job_id_from_request_path("/v1/reports"))
        self.assertIsNone(job_id_from_request_path("/health"))

    def test_log_event_is_json_serializable(self):
        tokens = bind_trace(request_id="req-3", correlation_id="corr-3", service="vein-reports")
        buffer = io.StringIO()
        original_stderr = sys.stderr
        try:
            sys.stderr = buffer
            log_event("info", "test_event", foo="bar")
            payload = json.loads(buffer.getvalue().strip())
            self.assertEqual(payload["event"], "test_event")
            self.assertEqual(payload["requestId"], "req-3")
            self.assertEqual(payload["correlationId"], "corr-3")
            self.assertEqual(payload["service"], "vein-reports")
        finally:
            sys.stderr = original_stderr
            reset_trace(tokens)


if __name__ == "__main__":
    unittest.main()
