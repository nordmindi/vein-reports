"""Build curated FinalReport objects from validated run state."""

from __future__ import annotations

import re
from typing import Any

from tradingagents.agents.utils.rating import parse_research_recommendation
from tradingagents.integrations.signal_validation_section import render_signal_validation_markdown
from tradingagents.report_composition.models import (
    SECTION_LIMITS,
    FinalReport,
    PortfolioManagerSynthesis,
    ReportMode,
)
from tradingagents.report_composition.sanitizer import (
    is_agent_process_paragraph,
    redact_forbidden_transaction_language,
    sanitize_for_publication,
    scan_blocked_report_text,
    truncate_words,
)

_RESEARCH_REC_DISPLAY = {
    "NO_CURRENT_TRANSACTION": "No current transaction",
    "WATCHLIST": "Watchlist",
    "TRADE_CANDIDATE": "Trade candidate",
    "RESEARCH_ONLY": "Research only",
    "INSUFFICIENT_EVIDENCE": "Insufficient evidence",
}

_LEGACY_RATING_TO_RESEARCH = {
    "Buy": "TRADE_CANDIDATE",
    "Overweight": "TRADE_CANDIDATE",
    "Hold": "WATCHLIST",
    "Underweight": "NO_CURRENT_TRANSACTION",
    "Sell": "NO_CURRENT_TRANSACTION",
    "Insufficient Evidence": "INSUFFICIENT_EVIDENCE",
    "NOT_AVAILABLE": "INSUFFICIENT_EVIDENCE",
}


def determine_report_mode(
    report_status: str,
    *,
    user_requested_full_report: bool = False,
) -> ReportMode:
    if report_status == "blocked":
        return ReportMode.BLOCKED
    if user_requested_full_report:
        return ReportMode.FULL
    return ReportMode.COMPACT


def _status_allows_action(status: str) -> bool:
    return status in {"verified"}


def _display_recommendation(code: str) -> str:
    return _RESEARCH_REC_DISPLAY.get(code, code.replace("_", " ").title())


def _research_recommendation_from_text(text: str, *, status: str) -> str:
    if not _status_allows_action(status):
        return "INSUFFICIENT_EVIDENCE"

    research = parse_research_recommendation(text, default="")
    if research:
        return research.upper().replace(" ", "_")

    rec_match = re.search(
        r"(?im)^\s*(?:\*\*)?(?:Recommendation|Rating)(?:\*\*)?\s*[:\-]\s*(.+)$",
        text,
    )
    if rec_match:
        raw = rec_match.group(1).strip().strip("*")
        normalized = raw.upper().replace(" ", "_").replace("-", "_")
        if normalized in _RESEARCH_REC_DISPLAY:
            return normalized
        for key, value in _RESEARCH_REC_DISPLAY.items():
            if raw.lower() == value.lower():
                return key

    from tradingagents.agents.utils.rating import parse_rating

    legacy = parse_rating(text, default="NOT_AVAILABLE")
    return _LEGACY_RATING_TO_RESEARCH.get(legacy, "INSUFFICIENT_EVIDENCE")


def _extract_thesis(text: str) -> str:
    patterns = (
        r"(?is)\*\*Synthesis\*\*\s*[:\-]?\s*(.+?)(?:\n\n\*\*|\Z)",
        r"(?is)\*\*Executive Summary\*\*\s*[:\-]?\s*(.+?)(?:\n\n\*\*|\Z)",
        r"(?is)\*\*Investment Thesis\*\*\s*[:\-]?\s*(.+?)(?:\n\n\*\*|\Z)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return sanitize_for_publication(match.group(1).strip())
    paragraphs = [p.strip() for p in sanitize_for_publication(text).split("\n\n") if p.strip()]
    return paragraphs[0] if paragraphs else ""


def _extract_bullet_lines(text: str, *, limit: int = 5) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")):
            bullet = stripped.lstrip("-*• ").strip()
            if bullet and len(bullet) > 12:
                bullets.append(sanitize_for_publication(bullet))
        if len(bullets) >= limit:
            break
    return bullets[:limit]


def _first_substantial_paragraph(text: str) -> str:
    cleaned = sanitize_for_publication(text)
    for block in cleaned.split("\n\n"):
        block = block.strip()
        if block.startswith("#"):
            continue
        if block.startswith("**") and block.endswith("**"):
            continue
        if is_agent_process_paragraph(block):
            continue
        if len(block.split()) >= 8:
            return block
    for block in cleaned.split("\n\n"):
        block = block.strip()
        if block and not is_agent_process_paragraph(block):
            return block
    return cleaned[:500].strip()


def compose_section_summary(
    raw_text: str,
    *,
    section_key: str,
    limitation: str | None = None,
) -> str:
    if not raw_text or not raw_text.strip():
        return ""

    max_words = SECTION_LIMITS.get(section_key, {}).get("max_words", 600)
    paragraph = truncate_words(_first_substantial_paragraph(raw_text), max_words // 3)
    bullets = _extract_bullet_lines(raw_text)
    if not bullets:
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        bullets = [s.strip() for s in sentences[:4] if len(s.split()) >= 5]

    lines = [paragraph, ""]
    if bullets:
        lines.append("**Key points:**")
        for bullet in bullets[:5]:
            lines.append(f"- {truncate_words(bullet, 40)}")
        lines.append("")

    limit_text = limitation or (
        "This section summarizes validated analyst observations only; "
        "it is not a transaction recommendation."
    )
    lines.append(f"**Limitations:** {limit_text}")
    return truncate_words("\n".join(lines), max_words)


def build_portfolio_synthesis(
    final_state: dict,
    validation_result: Any,
    *,
    market_summary: str = "",
    fundamentals_summary: str = "",
    news_sentiment_summary: str = "",
    signal_text: str = "",
) -> PortfolioManagerSynthesis:
    status = getattr(validation_result, "status", "research_only")
    final_decision = str(final_state.get("final_trade_decision", ""))
    recommendation = _research_recommendation_from_text(final_decision, status=status)
    action_allowed = _status_allows_action(status) and recommendation == "TRADE_CANDIDATE"
    publication_safe = _status_allows_action(status)

    blocking_issues = [
        issue.message.rstrip(".")
        for issue in getattr(validation_result, "blocking_issues", [])
    ][:8]

    if publication_safe:
        supportive = _extract_bullet_lines(final_decision, limit=3)
        summary_source = _extract_thesis(final_decision) or _first_substantial_paragraph(final_decision)
    else:
        supportive = []
        summary_source = (
            "Validation blocks transaction authority for this report. "
            "Treat the analysis as research context only."
        )
    if not supportive:
        supportive = _extract_bullet_lines(market_summary, limit=2)
    caution = _extract_bullet_lines(news_sentiment_summary, limit=2)
    if blocking_issues:
        caution = (caution + blocking_issues)[:5]

    confidence = "low"
    if status == "verified":
        confidence = "high"
    elif status == "verified_with_warnings" or recommendation == "WATCHLIST":
        confidence = "medium"

    required = []
    if not action_allowed:
        required.append("Report validation passes without blocking issues.")
    signal = final_state.get("golden_trend_signal") or {}
    if isinstance(signal, dict) and not signal.get("tradeAllowed", True):
        required.append("Signal service upgrades to trade allowed.")
        signal_text = signal_text or render_signal_validation_markdown(signal)

    return PortfolioManagerSynthesis(
        recommendation=recommendation,  # type: ignore[arg-type]
        confidence=confidence,
        action_allowed=action_allowed,
        summary=truncate_words(summary_source, 120),
        market_view=truncate_words(_first_substantial_paragraph(market_summary), 80),
        fundamentals_view=truncate_words(_first_substantial_paragraph(fundamentals_summary), 80),
        news_sentiment_view=truncate_words(_first_substantial_paragraph(news_sentiment_summary), 80),
        signal_service_view=truncate_words(signal_text, 100) if signal_text else None,
        key_supportive_points=supportive[:5],
        key_caution_points=caution[:5],
        required_confirmations=required[:5],
        blocking_issues=blocking_issues[:8],
    )


def build_executive_summary(
    *,
    report_mode: ReportMode,
    publication_status: str,
    synthesis: PortfolioManagerSynthesis,
    thesis: str,
    signal_text: str = "",
    blocking_reasons: list[str] | None = None,
    missing_evidence: list[str] | None = None,
) -> str:
    status_display = publication_status.replace("_", " ").title()
    rec_display = _display_recommendation(synthesis.recommendation)
    action = (
        _display_recommendation("NO_CURRENT_TRANSACTION")
        if not synthesis.action_allowed
        else rec_display
    )

    lines = [
        "## Executive Summary",
        "",
        f"**Report Status:** {status_display}",
        f"**Final Recommendation:** {rec_display}",
        f"**Action:** {action}",
        "",
        "**Thesis:**",
        truncate_words(thesis or synthesis.summary, 180),
        "",
    ]

    if synthesis.key_supportive_points:
        lines.append("**Key Supportive Points:**")
        for point in synthesis.key_supportive_points[:5]:
            lines.append(f"- {point}")
        lines.append("")

    if synthesis.key_caution_points:
        lines.append("**Key Caution Points:**")
        for point in synthesis.key_caution_points[:5]:
            lines.append(f"- {point}")
        lines.append("")

    if signal_text.strip():
        lines.extend(["**Signal Service Result:**", signal_text.strip(), ""])

    lines.extend(
        [
            "**Portfolio Manager View:**",
            truncate_words(synthesis.summary, 120),
            "",
        ]
    )

    if synthesis.required_confirmations:
        lines.append("**What Would Change the Decision:**")
        for item in synthesis.required_confirmations[:5]:
            lines.append(f"- {item}")
        lines.append("")

    data_issues = list(blocking_reasons or []) + list(missing_evidence or [])
    if data_issues:
        lines.append("**Data Quality / Blocking Issues:**")
        for issue in data_issues[:8]:
            lines.append(f"- {issue}")
        lines.append("")

    if report_mode == ReportMode.BLOCKED:
        lines.extend(
            [
                "**Decision:**",
                "No current transaction. Treat this report as research context only.",
                "",
            ]
        )

    return truncate_words("\n".join(lines), SECTION_LIMITS["executive_summary"]["max_words"])


def _collect_missing_evidence(validation_result: Any) -> list[str]:
    return [
        issue.message.rstrip(".")
        for issue in getattr(validation_result, "issues", [])
        if getattr(issue, "severity", "") == "blocking"
    ][:10]


def _collect_sources(final_state: dict) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    instrument = final_state.get("instrument_resolution") or {}
    if isinstance(instrument, dict) and instrument.get("selected_instrument_id"):
        sources.append(
            {
                "type": "instrument",
                "id": instrument.get("selected_instrument_id"),
                "source": (instrument.get("candidates") or [{}])[0].get("source", "unknown"),
            }
        )
    freshness = final_state.get("market_data_freshness") or {}
    if isinstance(freshness, dict) and freshness.get("provider"):
        sources.append(
            {
                "type": "market_data",
                "provider": freshness.get("provider"),
                "as_of": freshness.get("market_data_session"),
            }
        )
    return sources


def _historical_snapshot(final_state: dict) -> str:
    market = final_state.get("market_report") or ""
    if not market:
        return ""
    return compose_section_summary(
        market,
        section_key="market_summary",
        limitation="Historical snapshot for context only; not a trade setup.",
    )


def build_final_report(
    final_state: dict,
    ticker: str,
    validation_result: Any,
    dashboard_model: Any,
    *,
    user_requested_full_report: bool = False,
) -> FinalReport:
    status = getattr(validation_result, "status", "research_only")
    report_mode = determine_report_mode(status, user_requested_full_report=user_requested_full_report)
    is_blocked = report_mode == ReportMode.BLOCKED or not _status_allows_action(status)

    signal = final_state.get("golden_trend_signal")
    signal_text = ""
    if isinstance(signal, dict) and signal:
        signal_text = render_signal_validation_markdown(signal)

    market_raw = str(final_state.get("market_report") or "")
    fundamentals_raw = str(final_state.get("fundamentals_report") or "")
    news_raw = "\n\n".join(
        part
        for part in (
            final_state.get("news_report"),
            final_state.get("sentiment_report"),
        )
        if part
    )
    risk_raw = ""
    risk_state = final_state.get("risk_debate_state") or {}
    if isinstance(risk_state, dict):
        risk_raw = "\n\n".join(
            str(risk_state.get(key) or "")
            for key in ("aggressive_history", "conservative_history", "neutral_history")
        )

    market_summary = compose_section_summary(market_raw, section_key="market_summary") if market_raw else None
    fundamentals_summary = (
        compose_section_summary(fundamentals_raw, section_key="fundamentals_summary")
        if fundamentals_raw
        else None
    )
    news_summary = (
        compose_section_summary(news_raw, section_key="news_sentiment_summary") if news_raw else None
    )
    risk_summary = compose_section_summary(risk_raw, section_key="risks") if risk_raw and not is_blocked else None

    blocking_reasons = [
        redact_forbidden_transaction_language(issue.message.rstrip("."))
        for issue in getattr(validation_result, "blocking_issues", [])
    ]
    missing_evidence = [
        redact_forbidden_transaction_language(item)
        for item in _collect_missing_evidence(validation_result)
    ]

    synthesis = build_portfolio_synthesis(
        final_state,
        validation_result,
        market_summary=market_summary or "",
        fundamentals_summary=fundamentals_summary or "",
        news_sentiment_summary=news_summary or "",
        signal_text=signal_text,
    )

    if is_blocked:
        synthesis = synthesis.model_copy(
            update={
                "recommendation": "INSUFFICIENT_EVIDENCE",
                "action_allowed": False,
                "summary": redact_forbidden_transaction_language(
                    synthesis.summary
                    or "The report is blocked because validation did not pass publication thresholds."
                ),
                "key_supportive_points": [
                    redact_forbidden_transaction_language(point)
                    for point in synthesis.key_supportive_points
                ],
                "key_caution_points": [
                    redact_forbidden_transaction_language(point)
                    for point in synthesis.key_caution_points
                ],
            }
        )

    final_decision = str(final_state.get("final_trade_decision", ""))
    if is_blocked:
        thesis = redact_forbidden_transaction_language(
            _first_substantial_paragraph(
                "\n\n".join(filter(None, [market_raw[:400], fundamentals_raw[:200]]))
            )
        )
    else:
        thesis = _extract_thesis(final_decision) or _first_substantial_paragraph(
            "\n\n".join(filter(None, [market_raw[:400], fundamentals_raw[:200]]))
        )

    executive_summary = build_executive_summary(
        report_mode=report_mode,
        publication_status=status,
        synthesis=synthesis,
        thesis=thesis,
        signal_text=signal_text if not is_blocked else signal_text,
        blocking_reasons=blocking_reasons,
        missing_evidence=missing_evidence,
    )
    appendix = None
    if report_mode == ReportMode.FULL and user_requested_full_report:
        appendix_parts = []
        for label, raw in (
            ("Market Analyst", market_raw),
            ("Fundamentals Analyst", fundamentals_raw),
            ("News & Sentiment", news_raw),
        ):
            if raw:
                appendix_parts.append(f"### {label}\n{sanitize_for_publication(raw)}")
        appendix = "\n\n".join(appendix_parts) if appendix_parts else None

    if is_blocked:
        market_summary = _historical_snapshot(final_state) or market_summary
        fundamentals_summary = (
            compose_section_summary(
                fundamentals_raw,
                section_key="fundamentals_summary",
                limitation="Fundamental snapshot for context only.",
            )
            if fundamentals_raw
            else None
        )
        news_summary = None
        risk_summary = None
        signal_text = signal_text or None
        executive_summary = redact_forbidden_transaction_language(executive_summary)
        market_summary = (
            redact_forbidden_transaction_language(market_summary) if market_summary else None
        )
        fundamentals_summary = (
            redact_forbidden_transaction_language(fundamentals_summary)
            if fundamentals_summary
            else None
        )

    return FinalReport(
        symbol=ticker,
        company_name=final_state.get("company_of_interest"),
        report_mode=report_mode,
        publication_status=status,
        executive_summary=executive_summary,
        signal_validation=signal_text or None,
        market_summary=market_summary,
        fundamentals_summary=fundamentals_summary,
        news_sentiment_summary=news_summary,
        risk_summary=risk_summary,
        portfolio_synthesis=synthesis,
        blocking_reasons=blocking_reasons,
        missing_evidence=missing_evidence,
        sources=_collect_sources(final_state),
        appendix=appendix,
    )


def validate_blocked_report(final_report: FinalReport) -> list[str]:
    if _status_allows_action(final_report.publication_status):
        return []
    from tradingagents.report_composition.renderer import render_final_report_markdown

    return scan_blocked_report_text(render_final_report_markdown(final_report))
