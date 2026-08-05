
import pytest
from fastapi.testclient import TestClient

from tradingagents.service import api
from tradingagents.service.runner import ReportRequest, ReportResult


@pytest.mark.unit
class TestPersistedJobStore:
    def test_write_job_record_permission_error_returns_503(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path / "reports"))
        api.jobs.clear()
        record = api.JobRecord(
            "job-perm",
            ReportRequest(ticker="FCX", analysis_date="2026-08-05"),
        )

        def boom(*_args, **_kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(api.Path, "mkdir", boom)

        with pytest.raises(api.HTTPException) as exc_info:
            api._write_job_record(record)

        assert exc_info.value.status_code == 503
        assert "not writable" in str(exc_info.value.detail).lower()

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
        assert "job-running" in api.jobs

    def test_recover_marks_interrupted_running_jobs_failed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        monkeypatch.delenv("TRADINGAGENTS_JOB_RESUME_INTERRUPTED", raising=False)
        api.jobs.clear()
        record = api.JobRecord(
            "job-interrupted",
            ReportRequest(ticker="NVDA", analysis_date="2026-07-31"),
        )
        record.status = api.JobStatus.running
        api._write_job_record(record)
        api.jobs.clear()

        stats = api.recover_jobs_from_disk()

        assert stats["interrupted_failed"] == 1
        loaded = api.jobs["job-interrupted"]
        assert loaded.status == api.JobStatus.failed
        assert "interrupted by service restart" in (loaded.error or "").lower()

    def test_recover_requeues_queued_jobs(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        api.jobs.clear()
        record = api.JobRecord(
            "job-queued",
            ReportRequest(ticker="AAPL", analysis_date="2026-07-31"),
        )
        record.status = api.JobStatus.queued
        api._write_job_record(record)
        api.jobs.clear()

        submitted = []
        monkeypatch.setattr(
            api.executor,
            "submit",
            lambda fn, rec: submitted.append(rec.job_id) or None,
        )

        stats = api.recover_jobs_from_disk()

        assert stats["requeued"] == 1
        assert submitted == ["job-queued"]
        assert api.jobs["job-queued"].status == api.JobStatus.queued

    def test_recover_can_resume_interrupted_jobs(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        monkeypatch.setenv("TRADINGAGENTS_JOB_RESUME_INTERRUPTED", "1")
        api.jobs.clear()
        record = api.JobRecord(
            "job-resume",
            ReportRequest(ticker="MSFT", analysis_date="2026-07-31"),
        )
        record.status = api.JobStatus.running
        api._write_job_record(record)
        api.jobs.clear()

        submitted = []
        monkeypatch.setattr(
            api.executor,
            "submit",
            lambda fn, rec: submitted.append(rec.job_id) or None,
        )

        stats = api.recover_jobs_from_disk()

        assert stats["interrupted_resumed"] == 1
        assert submitted == ["job-resume"]
        assert api.jobs["job-resume"].status == api.JobStatus.queued

    def test_get_job_persists_strategy_id(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        api.jobs.clear()
        record = api.JobRecord(
            "job-strategy",
            ReportRequest(
                ticker="FCX",
                analysis_date="2026-07-05",
                strategy_id="golden-trend-aggressive",
            ),
        )
        record.status = api.JobStatus.queued
        api._write_job_record(record)
        api.jobs.clear()

        loaded = api._get_job("job-strategy")

        assert loaded.request.strategy_id == "golden-trend-aggressive"

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
            metrics={
                "version": "report-metrics-v1",
                "usage": {"llm_calls": 5, "tool_calls": 2, "tokens_in": 1000, "tokens_out": 200},
                "estimated_cost_usd": 0.12,
            },
        )
        api._write_job_record(record)
        api.jobs.clear()

        loaded = api._get_job("job-completed")

        assert loaded.status == api.JobStatus.completed
        assert loaded.result is not None
        assert loaded.result.pdf_path == pdf_path
        assert loaded.result.decision == "INSUFFICIENT_EVIDENCE"
        assert loaded.result.metrics is not None
        assert loaded.result.metrics["usage"]["llm_calls"] == 5


@pytest.mark.unit
class TestServiceApiContract:
    def test_openapi_documents_vein_context_and_artifact_endpoints(self):
        schema = api.app.openapi()

        create_schema = schema["components"]["schemas"]["CreateReportRequest"]
        properties = create_schema["properties"]
        assert "context_bundle" in properties
        assert "report_tier" in properties
        assert "VeinContextBundle" in schema["components"]["schemas"]
        assert "/v1/reports/{job_id}/dashboard" in schema["paths"]
        assert "/v1/reports/{job_id}/validation" in schema["paths"]
        assert "/v1/reports/{job_id}/evidence" in schema["paths"]
        assert "/v1/reports/{job_id}/metrics" in schema["paths"]
        assert "ReportJobMetrics" in schema["components"]["schemas"]
        assert "/v1/report-validation-lite" in schema["paths"]
        assert "target" in create_schema["properties"]
        assert "IntelligenceTargetInput" in schema["components"]["schemas"]

    def test_create_report_request_accepts_sector_target(self):
        payload = api.CreateReportRequest(
            target={"type": "sector", "value": "mining"},
            analysis_date="2026-07-31",
        )
        assert payload.target is not None
        assert payload.target.to_target().type == "sector"
        assert payload.ticker is None

    def test_create_report_request_rejects_ticker_and_target(self):
        with pytest.raises(ValueError, match="not both"):
            api.CreateReportRequest(
                ticker="NVDA",
                target={"type": "sector", "value": "mining"},
                analysis_date="2026-07-31",
            )

    def test_create_report_endpoint_accepts_target(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_API_KEY", "test-key")
        monkeypatch.setattr(api.executor, "submit", lambda fn, record: None)
        api.jobs.clear()
        client = TestClient(api.app)
        response = client.post(
            "/v1/reports",
            headers={"X-API-Key": "test-key"},
            json={
                "target": {"type": "sector", "value": "mining"},
                "analysis_date": "2026-07-31",
                "selected_analysts": ["market", "news"],
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        record = api.jobs[job_id]
        assert record.request.ticker is None
        assert record.request.intelligence_target is not None
        assert record.request.intelligence_target.type == "sector"
        assert record.request.intelligence_target.value == "mining"

    def test_report_validation_lite_endpoint(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_API_KEY", "test-key")
        client = TestClient(api.app)
        response = client.post(
            "/v1/report-validation-lite",
            headers={"X-API-Key": "test-key"},
            json={
                "symbol": "FCX",
                "rawSignal": "ENTER_SHORT",
                "finalSignal": "WATCHLIST_ONLY",
                "tradeAllowed": False,
                "confidenceScore": 16,
                "topBlockers": ["PROPOSAL_GATE_FAILED"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["reportValidation"]["recommendation"] == "DEFER_TO_SIGNALS"
        assert body["reportValidation"]["status"] == "DEFERRED"

    def test_context_bundle_auto_adds_supply_chain_for_pro_jobs(self, monkeypatch):
        monkeypatch.setattr(api, "run_report_job", lambda request, job_id: None)
        payload = api.CreateReportRequest(
            ticker="TSLA",
            analysis_date="2026-06-30",
            selected_analysts=["market"],
            context_bundle={
                "version": "vein-context-v1",
                "primary_symbol": "TSLA",
                "has_graph_coverage": True,
                "company": {"name": "Tesla, Inc.", "symbol": "TSLA", "is_chokepoint": False},
                "anchor_elements": [{"name": "Electric vehicles"}],
                "downstream_products": [],
                "related_companies": [],
                "chokepoints": [],
                "peer_tickers_for_news": [],
                "watchlist_notes": None,
                "generated_at": "2026-06-30T18:00:00.000Z",
            },
        )

        context = payload.context_bundle.model_dump(mode="json")
        selected_analysts = list(payload.selected_analysts)
        if context is not None and "supply_chain" not in selected_analysts:
            selected_analysts.append("supply_chain")

        request = ReportRequest(
            ticker=payload.ticker,
            analysis_date=payload.analysis_date or "2026-06-30",
            selected_analysts=tuple(selected_analysts),
            context_bundle=context,
        )

        assert "supply_chain" in request.selected_analysts
        assert request.context_bundle["primary_symbol"] == "TSLA"

    def test_completed_job_artifact_endpoints(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", str(tmp_path))
        monkeypatch.delenv("TRADINGAGENTS_SERVICE_API_KEY", raising=False)
        api.jobs.clear()
        report_dir = tmp_path / "job-artifacts"
        report_dir.mkdir(parents=True)
        (report_dir / "dashboard.json").write_text(
            '{"recommendation":"INSUFFICIENT_EVIDENCE"}',
            encoding="utf-8",
        )
        (report_dir / "validation_report.json").write_text(
            '{"status":"blocked","issues":[]}',
            encoding="utf-8",
        )
        (report_dir / "decision_evidence_bundle.json").write_text(
            '{"canonical_fact_ids":[]}',
            encoding="utf-8",
        )
        markdown_path = report_dir / "complete_report.md"
        pdf_path = report_dir / "report.pdf"
        markdown_path.write_text("# Report", encoding="utf-8")
        pdf_path.write_bytes(b"%PDF-1.4")

        record = api.JobRecord(
            "job-artifacts",
            ReportRequest(ticker="TSLA", analysis_date="2026-06-30"),
        )
        record.status = api.JobStatus.completed
        record.result = ReportResult(
            job_id="job-artifacts",
            ticker="TSLA",
            analysis_date="2026-06-30",
            decision="INSUFFICIENT_EVIDENCE",
            report_dir=report_dir,
            markdown_path=markdown_path,
            pdf_path=pdf_path,
        )
        api.jobs[record.job_id] = record

        client = TestClient(api.app)

        dashboard = client.get("/v1/reports/job-artifacts/dashboard")
        validation = client.get("/v1/reports/job-artifacts/validation")
        evidence = client.get("/v1/reports/job-artifacts/evidence")

        assert dashboard.status_code == 200
        assert dashboard.json()["recommendation"] == "INSUFFICIENT_EVIDENCE"
        assert validation.status_code == 200
        assert validation.json()["status"] == "blocked"
        assert evidence.status_code == 200
        assert evidence.json()["canonical_fact_ids"] == []
