"""Reusable report-tree writer shared by the CLI and the programmatic API.

Writes a run's per-section markdown (analysts, research, trading, risk,
portfolio) plus a consolidated ``complete_report.md`` under ``save_path``. The
CLI and ``TradingAgentsGraph.save_reports`` both call this, so a headless / API
run produces the same on-disk report tree a CLI run does.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tradingagents.agents.utils.report_text import sanitize_agent_report_text
from tradingagents.report_composition import (
    FinalReport,
    build_final_report,
    render_final_report_markdown,
    soften_rhetorical_language,
    validate_blocked_report,
)
from tradingagents.validation import (
    DashboardModel,
    ValidationResult,
    build_dashboard_model,
    build_decision_evidence_bundle,
    rejected_claims,
    usable_historical_lessons,
    validate_final_state,
    verified_claims,
)
from tradingagents.validation.build_technical_validation import attach_technical_validation


def finalize_validation_artifacts(
    final_state: dict,
    *,
    validation_result: ValidationResult | None = None,
    dashboard_model: DashboardModel | None = None,
    expected_analysts: tuple[str, ...] | list[str] | None = None,
    strict_validation: bool = False,
) -> tuple[ValidationResult, DashboardModel]:
    """Build and validate publication artifacts in final-gate order."""
    _attach_technical_validation(final_state)
    validation_state = _validation_state_view(final_state)
    _attach_claim_artifacts(final_state)
    if validation_result is None:
        validation_result = validate_final_state(
            validation_state,
            expected_analysts=expected_analysts,
            strict_mode=strict_validation,
        )

    _attach_claim_artifacts(final_state)
    evidence_bundle = build_decision_evidence_bundle(final_state, validation_result)
    final_state["decision_evidence_bundle"] = evidence_bundle.model_dump(mode="json")

    dashboard_model = dashboard_model or build_dashboard_model(final_state, validation_result)
    final_state["dashboard_model"] = dashboard_model.model_dump(mode="json")
    validation_result = validate_final_state(
        validation_state,
        expected_analysts=expected_analysts,
        strict_mode=strict_validation,
    )

    rebuilt_dashboard = build_dashboard_model(final_state, validation_result)
    _attach_claim_artifacts(final_state)
    evidence_bundle = build_decision_evidence_bundle(final_state, validation_result)
    final_state["decision_evidence_bundle"] = evidence_bundle.model_dump(mode="json")
    validation_result = validate_final_state(
        validation_state,
        expected_analysts=expected_analysts,
        strict_mode=strict_validation,
    )
    if rebuilt_dashboard != dashboard_model:
        dashboard_model = rebuilt_dashboard
        final_state["dashboard_model"] = dashboard_model.model_dump(mode="json")
        validation_result = validate_final_state(
            validation_state,
            expected_analysts=expected_analysts,
            strict_mode=strict_validation,
        )

    return validation_result, dashboard_model


def write_report_tree(
    final_state: dict,
    ticker: str,
    save_path,
    *,
    validation_result: ValidationResult | None = None,
    dashboard_model: DashboardModel | None = None,
    expected_analysts: tuple[str, ...] | list[str] | None = None,
    strict_validation: bool = False,
    user_requested_full_report: bool = False,
) -> Path:
    """Save a completed run's reports to ``save_path``; return the complete-report path."""
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)

    validation_result, dashboard_model = finalize_validation_artifacts(
        final_state,
        validation_result=validation_result,
        dashboard_model=dashboard_model,
        expected_analysts=expected_analysts,
        strict_validation=strict_validation,
    )
    write_validation_report(save_path, validation_result)
    write_dashboard_report(save_path, dashboard_model)
    write_decision_evidence_report(save_path, final_state)
    write_claim_reports(save_path, final_state)

    if strict_validation and validation_result.has_blocking_issues:
        codes = ", ".join(issue.code for issue in validation_result.blocking_issues)
        raise ValueError(f"Report validation blocked publication: {codes}")

    _write_audit_report_tree(final_state, save_path, validation_result, dashboard_model)

    final_report = build_final_report(
        final_state,
        ticker,
        validation_result,
        dashboard_model,
        user_requested_full_report=user_requested_full_report,
    )
    violations = validate_blocked_report(final_report)
    if violations:
        raise ValueError(
            "Blocked report contains forbidden transaction language: "
            + ", ".join(violations)
        )

    write_final_report_artifacts(save_path, final_report)
    report_path = save_path / "complete_report.md"
    report_path.write_text(render_final_report_markdown(final_report), encoding="utf-8")
    return report_path


def _write_audit_report_tree(
    final_state: dict,
    save_path: Path,
    validation_result: ValidationResult,
    dashboard_model: DashboardModel,
) -> None:
    """Persist raw agent outputs for audit; excluded from the published report."""
    signal = final_state.get("golden_trend_signal")
    if isinstance(signal, dict) and signal:
        from tradingagents.integrations.signal_validation_section import (
            write_signal_validation_artifacts,
        )

        write_signal_validation_artifacts(save_path, signal)

    intelligence_bundle = final_state.get("vein_intelligence_bundle")
    intelligence_briefs = final_state.get("vein_intelligence_briefs")
    if isinstance(intelligence_bundle, dict) or isinstance(intelligence_briefs, dict):
        from tradingagents.integrations.intelligence_artifact import write_intelligence_artifacts

        write_intelligence_artifacts(
            save_path,
            intelligence_bundle if isinstance(intelligence_bundle, dict) else None,
            intelligence_briefs if isinstance(intelligence_briefs, dict) else None,
        )

    analysts_dir = save_path / "1_analysts"
    for key, filename in (
        ("market_report", "market.md"),
        ("sentiment_report", "sentiment.md"),
        ("news_report", "news.md"),
        ("fundamentals_report", "fundamentals.md"),
        ("supply_chain_report", "supply_chain.md"),
    ):
        if final_state.get(key):
            analysts_dir.mkdir(exist_ok=True)
            (analysts_dir / filename).write_text(
                sanitize_agent_report_text(final_state[key]),
                encoding="utf-8",
            )

    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        for key, filename in (
            ("bull_history", "bull.md"),
            ("bear_history", "bear.md"),
            ("judge_decision", "manager.md"),
        ):
            if debate.get(key):
                research_dir.mkdir(exist_ok=True)
                (research_dir / filename).write_text(
                    sanitize_agent_report_text(debate[key]),
                    encoding="utf-8",
                )

    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(
            sanitize_agent_report_text(final_state["trader_investment_plan"]),
            encoding="utf-8",
        )

    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        for key, filename in (
            ("aggressive_history", "aggressive.md"),
            ("conservative_history", "conservative.md"),
            ("neutral_history", "neutral.md"),
        ):
            if risk.get(key):
                risk_dir.mkdir(exist_ok=True)
                (risk_dir / filename).write_text(
                    sanitize_agent_report_text(risk[key]),
                    encoding="utf-8",
                )

        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            portfolio_decision = _published_portfolio_decision(
                raw_decision=sanitize_agent_report_text(risk["judge_decision"]),
                validation_result=validation_result,
                dashboard_model=dashboard_model,
            )
            (portfolio_dir / "decision.md").write_text(portfolio_decision, encoding="utf-8")


def write_final_report_artifacts(save_path: Path, final_report: FinalReport) -> None:
    report_path = save_path / "final_report.json"
    report_path.write_text(
        json.dumps(final_report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )


def save_report_to_disk(final_state: dict[str, Any], ticker: str, save_path: Path) -> Path:
    """Save a complete analysis report to disk with organized subfolders."""
    return write_report_tree(final_state, ticker, save_path)


def generate_pdf_from_markdown(
    md_path: Path,
    ticker: str,
    output_path: Path,
    *,
    validation_result: ValidationResult | None = None,
    dashboard_model: DashboardModel | None = None,
    executive_summary: str | None = None,
) -> Path:
    """Generate a PDF report from an existing markdown report."""
    MarkdownPDFGenerator = _load_markdown_pdf_generator()

    content = sanitize_agent_report_text(md_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary_text = executive_summary or _extract_executive_summary(content)

    generator = MarkdownPDFGenerator(
        ticker=ticker,
        date_str=dt.datetime.now().strftime("%B %d, %Y"),
        status_label=(
            validation_result.status_label
            if validation_result is not None
            else "RESEARCH_OUTPUT"
        ),
    )
    generator.add_executive_summary_page(summary_text)
    body = _pdf_body_without_executive_summary(content)
    generator.add_markdown_content(body)
    generator.save(str(output_path))
    return output_path


def _extract_executive_summary(content: str) -> str:
    marker = "## Executive Summary"
    if marker not in content:
        return content[:2000]
    start = content.index(marker)
    remainder = content[start + len(marker) :]
    next_heading = remainder.find("\n## ")
    section = remainder if next_heading == -1 else remainder[:next_heading]
    return marker + section.strip()


def _pdf_body_without_executive_summary(content: str) -> str:
    marker = "## Executive Summary"
    if marker not in content:
        return content
    start = content.index(marker)
    remainder = content[start + len(marker) :]
    next_heading = remainder.find("\n## ")
    if next_heading == -1:
        return content[:start].strip()
    return (content[:start] + remainder[next_heading:]).strip()


def write_validation_report(save_path: Path, validation_result: ValidationResult) -> None:
    report_path = save_path / "validation_report.json"
    report_path.write_text(
        json.dumps(validation_result.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )


def write_dashboard_report(save_path: Path, dashboard_model: DashboardModel) -> None:
    report_path = save_path / "dashboard.json"
    report_path.write_text(
        json.dumps(dashboard_model.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )


def write_decision_evidence_report(save_path: Path, final_state: dict) -> None:
    bundle = final_state.get("decision_evidence_bundle") or {}
    bundle_path = save_path / "decision_evidence_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    lessons = [
        lesson.model_dump(mode="json")
        for lesson in usable_historical_lessons(final_state)
    ]
    lessons_path = save_path / "validated_lessons.json"
    lessons_path.write_text(json.dumps(lessons, indent=2), encoding="utf-8")


def write_claim_reports(save_path: Path, final_state: dict) -> None:
    verified_path = save_path / "verified_claims.json"
    verified_path.write_text(
        json.dumps(final_state.get("verified_claims") or [], indent=2),
        encoding="utf-8",
    )

    rejected_path = save_path / "rejected_claims.json"
    rejected_path.write_text(
        json.dumps(final_state.get("rejected_claims") or [], indent=2),
        encoding="utf-8",
    )


def _attach_technical_validation(final_state: dict) -> None:
    symbol = str(
        final_state.get("company_of_interest")
        or final_state.get("ticker")
        or ""
    ).strip()
    trade_date = str(final_state.get("trade_date") or "").strip()
    if not symbol or not trade_date:
        return
    attach_technical_validation(final_state, symbol, trade_date)


def _validation_state_view(final_state: dict) -> dict:
    """Copy of run state with rhetoric softened for publication validation only."""
    view = deepcopy(final_state)
    for key in (
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    ):
        if view.get(key):
            view[key] = soften_rhetorical_language(str(view[key]))

    for debate_key in ("investment_debate_state", "risk_debate_state"):
        debate = view.get(debate_key)
        if not isinstance(debate, dict):
            continue
        for key, value in list(debate.items()):
            if isinstance(value, str) and value:
                debate[key] = soften_rhetorical_language(value)

    return view


def _attach_claim_artifacts(final_state: dict) -> None:
    final_state["verified_claims"] = [
        claim.model_dump(mode="json") for claim in verified_claims(final_state)
    ]
    final_state["rejected_claims"] = [
        claim.model_dump(mode="json") for claim in rejected_claims(final_state)
    ]


def _published_portfolio_decision(
    *,
    raw_decision: str,
    validation_result: ValidationResult,
    dashboard_model: DashboardModel,
) -> str:
    if dashboard_model.decision_status == "available":
        return raw_decision

    reasons = [
        issue.message.rstrip(".")
        for issue in validation_result.blocking_issues[:5]
    ]
    if not reasons:
        reasons = [
            "The report status is research-only, so the final model output has not met the publication threshold for transaction authority",
            "The decision evidence bundle does not contain verified directional evidence sufficient for an actionable portfolio rating",
        ]

    reason_lines = "\n".join(f"- {reason}." for reason in reasons)
    return (
        "**Recommendation**: Insufficient Evidence\n\n"
        "**Action**: No current transaction\n\n"
        "**Synthesis**: The validation layer blocks transaction authority for "
        "this report. Any raw directional Portfolio Manager output from the "
        "model is treated as non-published research context, not as an "
        "actionable recommendation.\n\n"
        f"**Blocking issues**:\n{reason_lines}"
    )


def _load_markdown_pdf_generator() -> type:
    try:
        from scripts.generate_full_report_pdf import MarkdownPDFGenerator

        return MarkdownPDFGenerator
    except ModuleNotFoundError:
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "generate_full_report_pdf.py"
        if not script_path.exists():
            raise

        spec = importlib.util.spec_from_file_location(
            "tradingagents_generate_full_report_pdf",
            script_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load PDF generator from {script_path}") from None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.MarkdownPDFGenerator
