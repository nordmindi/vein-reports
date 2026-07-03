from pathlib import Path

import pytest

from tradingagents.service import api
from tradingagents.service.runner import ReportRequest, ReportResult


@pytest.mark.unit
class TestPersistedJobStore:
    def test_get_job_loads_persisted_running_record(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        api.jobs.clear()
        record = api.JobRecord(
            "job-running",
            ReportRequest(ticker="TSLA", analysis_date="2026-06-30"),
        )
        record.status = api.JobStatus.running
        api._write_job_record(record)
        api.jobs.clear()

        loaded = api._get_job("job-running")

        assert loaded.job_id == "job-running"
        assert loaded.status == api.JobStatus.running
        assert loaded.request.ticker == "TSLA"

    def test_get_job_loads_persisted_completed_record(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        api.jobs.clear()
        report_dir = tmp_path / "job-completed"
        markdown_path = report_dir / "complete_report.md"
        pdf_path = report_dir / "report.pdf"
        record = api.JobRecord(
            "job-completed",
            ReportRequest(ticker="TSLA", analysis_date="2026-06-30"),
        )
        record.status = api.JobStatus.completed
        record.result = ReportResult(
            job_id="job-completed",
            ticker="TSLA",
            analysis_date="2026-06-30",
            decision="INSUFFICIENT_EVIDENCE",
            report_dir=report_dir,
            markdown_path=markdown_path,
            pdf_path=pdf_path,
        )
        api._write_job_record(record)
        api.jobs.clear()

        loaded = api._get_job("job-completed")

        assert loaded.status == api.JobStatus.completed
        assert loaded.result is not None
        assert loaded.result.pdf_path == pdf_path
        assert loaded.result.decision == "INSUFFICIENT_EVIDENCE"
