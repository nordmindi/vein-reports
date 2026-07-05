
import pytest
from fastapi.testclient import TestClient

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
