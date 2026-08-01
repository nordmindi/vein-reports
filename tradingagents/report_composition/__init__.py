"""Curated report composition for publication-safe PDF and markdown output."""

from tradingagents.report_composition.composer import (
    build_executive_summary,
    build_final_report,
    build_portfolio_synthesis,
    compose_section_summary,
    determine_report_mode,
    validate_blocked_report,
)
from tradingagents.report_composition.models import (
    AGENT_PROCESS_PHRASES,
    AGENT_PROCESS_REGEXES,
    BLOCKED_FORBIDDEN_TERMS,
    SECTION_LIMITS,
    FinalReport,
    PortfolioManagerSynthesis,
    ReportMode,
)
from tradingagents.report_composition.renderer import (
    render_final_report_markdown,
    render_portfolio_synthesis_section,
)
from tradingagents.report_composition.sanitizer import (
    is_agent_process_paragraph,
    redact_forbidden_transaction_language,
    sanitize_for_publication,
    scan_blocked_report_text,
    strip_agent_process_phrases,
    truncate_words,
)

__all__ = [
    "AGENT_PROCESS_PHRASES",
    "AGENT_PROCESS_REGEXES",
    "BLOCKED_FORBIDDEN_TERMS",
    "FinalReport",
    "PortfolioManagerSynthesis",
    "ReportMode",
    "SECTION_LIMITS",
    "build_executive_summary",
    "build_final_report",
    "build_portfolio_synthesis",
    "compose_section_summary",
    "determine_report_mode",
    "render_final_report_markdown",
    "render_portfolio_synthesis_section",
    "is_agent_process_paragraph",
    "sanitize_for_publication",
    "scan_blocked_report_text",
    "strip_agent_process_phrases",
    "truncate_words",
    "validate_blocked_report",
]
