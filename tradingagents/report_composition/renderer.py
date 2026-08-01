"""Render FinalReport objects to publication markdown."""

from __future__ import annotations

import datetime as dt
import re

from tradingagents.report_composition.models import FinalReport, ReportMode
from tradingagents.report_composition.sanitizer import (
    clean_publication_excerpt,
    is_section_header_only,
)


def _display_recommendation(code: str) -> str:
    mapping = {
        "NO_CURRENT_TRANSACTION": "No current transaction",
        "WATCHLIST": "Watchlist",
        "TRADE_CANDIDATE": "Trade candidate",
        "RESEARCH_ONLY": "Research only",
        "INSUFFICIENT_EVIDENCE": "Insufficient evidence",
    }
    return mapping.get(code, code.replace("_", " ").title())


def render_portfolio_synthesis_section(final_report: FinalReport) -> str:
    s = final_report.portfolio_synthesis
    lines = [
        "## Portfolio Manager Synthesis",
        "",
        f"**Recommendation:** {_display_recommendation(s.recommendation)}",
        f"**Action:** {_display_recommendation('NO_CURRENT_TRANSACTION') if not s.action_allowed else _display_recommendation(s.recommendation)}",
        f"**Confidence:** {s.confidence.title()}",
        "",
    "**Synthesis:**",
    clean_publication_excerpt(s.summary)
    if clean_publication_excerpt(s.summary)
    and not is_section_header_only(clean_publication_excerpt(s.summary))
    else "Research context only; no transaction authority.",
    "",
    ]
    if s.key_supportive_points:
        lines.append("**Supportive points:**")
        for point in s.key_supportive_points:
            lines.append(f"- {point}")
        lines.append("")
    if s.key_caution_points:
        lines.append("**Caution points:**")
        for point in s.key_caution_points:
            lines.append(f"- {point}")
        lines.append("")
    if s.required_confirmations:
        lines.append("**Required confirmations:**")
        for item in s.required_confirmations:
            lines.append(f"- {item}")
        lines.append("")
    lines.append(
        f"**Final view:** {_display_recommendation('NO_CURRENT_TRANSACTION') if not s.action_allowed else _display_recommendation(s.recommendation)}."
    )
    return "\n".join(lines)


def render_final_report_markdown(final_report: FinalReport) -> str:
    header = (
        f"# Trading Analysis Report: {final_report.symbol}\n\n"
        f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    sections: list[str] = [final_report.executive_summary]

    if final_report.report_mode == ReportMode.BLOCKED:
        # Blocking reasons already appear in the Executive Summary; keep a
        # dedicated section only when the summary omitted them (empty thesis path).
        if final_report.blocking_reasons and "**Data Quality / Blocking Issues:**" not in (
            final_report.executive_summary or ""
        ):
            lines = ["## Blocking Reasons", ""]
            for reason in final_report.blocking_reasons:
                lines.append(f"- {reason}")
            sections.append("\n".join(lines))

        if final_report.market_summary:
            sections.append(f"## Historical Snapshot\n\n{final_report.market_summary}")

        if final_report.fundamentals_summary:
            sections.append(f"## Fundamental Snapshot\n\n{final_report.fundamentals_summary}")

        # Skip Missing Evidence when it would only repeat blocking reasons.
        blocking_set = {
            re.sub(r"\s+", " ", r).strip().lower()
            for r in (final_report.blocking_reasons or [])
        }
        missing = [
            item
            for item in (final_report.missing_evidence or [])
            if re.sub(r"\s+", " ", item).strip().lower() not in blocking_set
        ]
        if missing:
            lines = ["## Missing Evidence", ""]
            for item in missing:
                lines.append(f"- {item}")
            sections.append("\n".join(lines))

        if final_report.signal_validation:
            sections.append(final_report.signal_validation)

        if final_report.sources:
            lines = ["## Sources", ""]
            for source in final_report.sources:
                parts = ", ".join(f"{k}: {v}" for k, v in source.items())
                lines.append(f"- {parts}")
            sections.append("\n".join(lines))

        return header + "\n\n".join(sections)

    if final_report.signal_validation:
        sections.append(final_report.signal_validation)

    if final_report.market_summary:
        sections.append(f"## Market / Technical Summary\n\n{final_report.market_summary}")

    if final_report.fundamentals_summary:
        sections.append(f"## Fundamentals Summary\n\n{final_report.fundamentals_summary}")

    if final_report.news_sentiment_summary:
        sections.append(f"## News and Sentiment Summary\n\n{final_report.news_sentiment_summary}")

    if final_report.risk_summary:
        sections.append(f"## Key Risks\n\n{final_report.risk_summary}")

    sections.append(render_portfolio_synthesis_section(final_report))

    if final_report.sources:
        lines = ["## Sources", ""]
        for source in final_report.sources:
            parts = ", ".join(f"{k}: {v}" for k, v in source.items())
            lines.append(f"- {parts}")
        sections.append("\n".join(lines))

    if final_report.appendix and final_report.report_mode == ReportMode.FULL:
        sections.append(f"## Appendix\n\n{final_report.appendix}")

    return header + "\n\n".join(sections)
