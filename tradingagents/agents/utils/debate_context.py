"""Shared analyst context for debate and risk agents."""

from __future__ import annotations

_REPORT_FIELDS = (
    ("market_report", "Market"),
    ("sentiment_report", "Sentiment"),
    ("news_report", "News"),
    ("fundamentals_report", "Fundamentals"),
    ("supply_chain_report", "Supply Chain"),
)


def format_debate_analyst_context(state: dict) -> str:
    """Return analyst context for downstream debate agents."""
    brief = str(state.get("debate_brief") or "").strip()
    if brief:
        return f"Analyst brief (compressed):\n{brief}"

    sections: list[str] = []
    for field, label in _REPORT_FIELDS:
        text = str(state.get(field) or "").strip()
        if text:
            sections.append(f"{label} report:\n{text}")

    if not sections:
        return "(No analyst reports available)"
    return "\n\n".join(sections)


def collect_analyst_reports_for_brief(state: dict) -> str:
    """Concatenate full analyst reports for the debate-brief compression step."""
    sections: list[str] = []
    for field, label in _REPORT_FIELDS:
        text = str(state.get(field) or "").strip()
        if text:
            sections.append(f"## {label}\n{text}")
    return "\n\n".join(sections)
