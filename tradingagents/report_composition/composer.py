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
    clean_publication_excerpt,
    is_agent_process_paragraph,
    is_section_header_only,
    redact_forbidden_transaction_language,
    sanitize_for_publication,
    scan_blocked_report_text,
    soften_rhetorical_language,
    strip_agent_process_phrases,
    truncate_words,
)


def _publication_safe(text: str) -> str:
    """Neutralize rhetoric and redact transaction terms for published copy."""
    return soften_rhetorical_language(redact_forbidden_transaction_language(text))


_MISSING_EVIDENCE_CODES = frozenset(
    {
        "FAILED_REQUIRED_AGENT",
        "FINAL_RECOMMENDATION_MISSING",
        "NEWS_VENDOR_COVERAGE_FAILURE",
        "PEER_NEWS_FALLBACK_FAILED",
        "NO_DATA_AVAILABLE",
    }
)


def _summarize_blocking_message(code: str, message: str) -> str:
    """Collapse noisy validation messages into short publication lines."""
    text = (message or "").strip().rstrip(".")
    if code == "RHETORICAL_LANGUAGE":
        # Do not echo the banned word into published copy (softening would
        # rewrite e.g. 'catastrophic' → 'severe' and look broken).
        return "Prohibited rhetorical or non-neutral language detected in agent output"
    if code == "UNAUTHORIZED_RECOMMENDATION":
        return "Specialist report contained an unauthorized recommendation line"
    if code == "UNSUPPORTED_STREAK_CLAIM" and text.lower().startswith(
        "rejected downstream claim"
    ):
        return "Sequence or streak claims require complete calculation evidence"
    if len(text) > 160:
        return text[:157].rstrip() + "…"
    return text


def collect_publication_blocking_reasons(
    validation_result: Any,
    *,
    limit: int = 8,
) -> list[str]:
    """Unique, short blocking reasons for executive summary / blocked sections.

    Deduplicates identical diagnostics that the validator emits once per
    location (e.g. five identical death-cross issues).
    """
    seen: set[str] = set()
    reasons: list[str] = []
    for issue in getattr(validation_result, "blocking_issues", []) or []:
        code = str(getattr(issue, "code", "") or "")
        message = str(getattr(issue, "message", "") or "")
        summary = _summarize_blocking_message(code, message)
        # Redact transaction terms only — never soften diagnostic text.
        summary = redact_forbidden_transaction_language(summary)
        key = re.sub(r"\s+", " ", summary).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        reasons.append(summary)
        if len(reasons) >= limit:
            break
    return reasons

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


def _is_publication_blocked(status: str, report_mode: ReportMode) -> bool:
    return report_mode == ReportMode.BLOCKED or status == "blocked"


def _suppress_trade_action(status: str) -> bool:
    return not _status_allows_action(status)


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
            excerpt = clean_publication_excerpt(match.group(1).strip())
            if excerpt and not is_section_header_only(excerpt):
                return soften_rhetorical_language(excerpt)
    for block in clean_publication_excerpt(text).split("\n\n"):
        block = block.strip()
        if (
            block
            and not is_section_header_only(block)
            and not is_agent_process_paragraph(block)
            and len(block.split()) >= 8
        ):
            return soften_rhetorical_language(block)
    return ""


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


def _extract_markdown_section(text: str, *headings: str) -> str:
    for heading in headings:
        pattern = rf"(?is)^#{{1,3}}\s*{re.escape(heading)}\s*$(.+?)(?=^#{{1,3}}\s|\Z)"
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            continue
        body = strip_agent_process_phrases(match.group(1).strip())
        if body:
            return body
    return ""


def _first_substantial_paragraph(text: str) -> str:
    section = _extract_markdown_section(text, "Executive Summary", "Summary", "1. Company Overview")
    if section:
        for block in section.split("\n\n"):
            block = strip_agent_process_phrases(block.strip())
            if block and not is_agent_process_paragraph(block) and len(block.split()) >= 8:
                return block

    cleaned = sanitize_for_publication(text)
    for block in cleaned.split("\n\n"):
        block = block.strip()
        if not block or block == "---":
            continue
        if block.startswith("#"):
            continue
        if block.startswith("**Analysis Date:"):
            continue
        if re.fullmatch(r"\*\*[^*]+\*\*", block):
            continue
        block = clean_publication_excerpt(block)
        if is_section_header_only(block):
            continue
        if is_agent_process_paragraph(block):
            continue
        if len(block.split()) >= 8:
            return block
    for block in cleaned.split("\n\n"):
        block = clean_publication_excerpt(block.strip())
        if block and not is_section_header_only(block) and not is_agent_process_paragraph(block):
            return block
    return clean_publication_excerpt(cleaned[:500].strip())


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

    blocking_issues = collect_publication_blocking_reasons(validation_result, limit=8)

    if publication_safe:
        supportive = _extract_bullet_lines(final_decision, limit=3)
        summary_source = _extract_thesis(final_decision) or _first_substantial_paragraph(final_decision)
    elif status != "blocked":
        supportive = _extract_bullet_lines(final_decision, limit=3)
        summary_source = (
            _extract_thesis(final_decision)
            or _first_substantial_paragraph(market_summary)
            or "Research context only; no transaction authority."
        )
    else:
        supportive = []
        summary_source = (
            "Validation blocks transaction authority for this report. "
            "Treat the analysis as research context only."
        )
    if not supportive:
        supportive = _extract_bullet_lines(market_summary, limit=2)
    # Keep caution points narrative-only; blocking reasons are listed separately.
    caution = _extract_bullet_lines(news_sentiment_summary, limit=3)

    confidence = "low"
    if status == "verified":
        confidence = "high"
    elif status == "verified_with_warnings" or recommendation == "WATCHLIST":
        confidence = "medium"

    required = []
    if status == "blocked":
        required.append("Report validation passes without blocking issues.")
    signal = final_state.get("golden_trend_signal") or {}
    if isinstance(signal, dict) and not signal.get("tradeAllowed", True):
        required.append("Signal service upgrades to trade allowed.")
        signal_text = signal_text or render_signal_validation_markdown(signal)

    return PortfolioManagerSynthesis(
        recommendation=recommendation,  # type: ignore[arg-type]
        confidence=confidence,
        action_allowed=action_allowed,
        summary=truncate_words(
            clean_publication_excerpt(summary_source)
            if not is_section_header_only(clean_publication_excerpt(summary_source))
            else "Research context only; no transaction authority.",
            120,
        ),
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

    summary_view = clean_publication_excerpt(synthesis.summary)
    thesis_view = clean_publication_excerpt(thesis or "")
    if (
        summary_view
        and not is_section_header_only(summary_view)
        and summary_view.lower() != thesis_view.lower()
    ):
        lines.extend(
            [
                "**Portfolio Manager View:**",
                truncate_words(summary_view, 120),
                "",
            ]
        )

    if synthesis.required_confirmations:
        lines.append("**What Would Change the Decision:**")
        for item in synthesis.required_confirmations[:5]:
            lines.append(f"- {item}")
        lines.append("")

    # Prefer explicit blocking reasons; fall back to missing-evidence only when
    # no blocking list was provided (avoid duplicating the same lines twice).
    data_issues = list(blocking_reasons or []) or list(missing_evidence or [])
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


def _build_appendix(
    final_state: dict,
    *,
    market_raw: str,
    fundamentals_raw: str,
    news_raw: str,
) -> str | None:
    parts: list[str] = []
    for label, raw in (
        ("Market Analyst", market_raw),
        ("Fundamentals Analyst", fundamentals_raw),
        ("News & Sentiment", news_raw),
    ):
        if raw.strip():
            parts.append(f"### {label}\n{_publication_safe(raw)}")

    debate = final_state.get("investment_debate_state") or {}
    if isinstance(debate, dict):
        research_raw = "\n\n".join(
            str(debate.get(key) or "")
            for key in ("bull_history", "bear_history", "judge_decision")
        )
        if research_raw.strip():
            parts.append(f"### Research Debate\n{_publication_safe(research_raw)}")

    risk_state = final_state.get("risk_debate_state") or {}
    if isinstance(risk_state, dict):
        risk_raw = "\n\n".join(
            str(risk_state.get(key) or "")
            for key in (
                "aggressive_history",
                "conservative_history",
                "neutral_history",
                "judge_decision",
            )
        )
        if risk_raw.strip():
            parts.append(f"### Risk Debate\n{_publication_safe(risk_raw)}")

    for label, key in (
        ("Trader Plan", "trader_investment_plan"),
        ("Portfolio Decision", "final_trade_decision"),
    ):
        raw = str(final_state.get(key) or "")
        if raw.strip():
            parts.append(f"### {label}\n{_publication_safe(raw)}")

    return "\n\n".join(parts) if parts else None


def _collect_missing_evidence(validation_result: Any) -> list[str]:
    """Return distinct missing-evidence diagnostics (not all blocking issues)."""
    seen: set[str] = set()
    items: list[str] = []
    for issue in getattr(validation_result, "issues", []) or []:
        if getattr(issue, "severity", "") != "blocking":
            continue
        code = str(getattr(issue, "code", "") or "")
        if code not in _MISSING_EVIDENCE_CODES:
            continue
        summary = _summarize_blocking_message(
            code, str(getattr(issue, "message", "") or "")
        )
        summary = redact_forbidden_transaction_language(summary)
        key = summary.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(summary)
        if len(items) >= 8:
            break
    return items


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
    is_publication_blocked = _is_publication_blocked(status, report_mode)
    suppress_trade_action = _suppress_trade_action(status)

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
    risk_summary = (
        compose_section_summary(risk_raw, section_key="risks")
        if risk_raw and not is_publication_blocked
        else None
    )

    blocking_reasons = collect_publication_blocking_reasons(validation_result, limit=8)
    missing_evidence = _collect_missing_evidence(validation_result)

    synthesis = build_portfolio_synthesis(
        final_state,
        validation_result,
        market_summary=market_summary or "",
        fundamentals_summary=fundamentals_summary or "",
        news_sentiment_summary=news_summary or "",
        signal_text=signal_text,
    )

    if suppress_trade_action:
        synthesis = synthesis.model_copy(
            update={
                "recommendation": "INSUFFICIENT_EVIDENCE",
                "action_allowed": False,
                "summary": _publication_safe(
                    synthesis.summary
                    if not is_publication_blocked
                    else (
                        synthesis.summary
                        or "The report is blocked because validation did not pass publication thresholds."
                    )
                ),
                "key_supportive_points": [
                    _publication_safe(point) for point in synthesis.key_supportive_points
                ],
                "key_caution_points": [
                    _publication_safe(point) for point in synthesis.key_caution_points
                ],
            }
        )

    final_decision = str(final_state.get("final_trade_decision", ""))
    if suppress_trade_action:
        thesis = _publication_safe(
            _extract_thesis(final_decision)
            or _first_substantial_paragraph(
                "\n\n".join(filter(None, [market_raw, fundamentals_raw]))
            )
        )
    else:
        thesis = soften_rhetorical_language(
            _extract_thesis(final_decision)
            or _first_substantial_paragraph(
                "\n\n".join(filter(None, [market_raw, fundamentals_raw]))
            )
        )

    executive_summary = build_executive_summary(
        report_mode=report_mode,
        publication_status=status,
        synthesis=synthesis,
        thesis=thesis,
        signal_text=signal_text,
        blocking_reasons=blocking_reasons,
        missing_evidence=missing_evidence,
    )
    appendix = None
    if report_mode == ReportMode.FULL and user_requested_full_report:
        appendix = _build_appendix(
            final_state,
            market_raw=market_raw,
            fundamentals_raw=fundamentals_raw,
            news_raw=news_raw,
        )

    if is_publication_blocked:
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
        executive_summary = _publication_safe(executive_summary)
        market_summary = _publication_safe(market_summary) if market_summary else None
        fundamentals_summary = (
            _publication_safe(fundamentals_summary) if fundamentals_summary else None
        )
    else:
        executive_summary = soften_rhetorical_language(executive_summary)
        market_summary = (
            soften_rhetorical_language(market_summary) if market_summary else None
        )
        fundamentals_summary = (
            soften_rhetorical_language(fundamentals_summary)
            if fundamentals_summary
            else None
        )
        news_summary = soften_rhetorical_language(news_summary) if news_summary else None
        risk_summary = soften_rhetorical_language(risk_summary) if risk_summary else None
        if signal_text:
            signal_text = soften_rhetorical_language(signal_text)

    return FinalReport(
        symbol=ticker,
        company_name=final_state.get("report_display_label")
        or final_state.get("company_of_interest"),
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
