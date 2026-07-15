"""Sanitize raw LLM agent text before publication in markdown or PDF reports."""

from __future__ import annotations

import re

_TOOL_CALL_BLOCKS = (
    r"<tool_call\b[^>]*>.*?</tool_call>",
    r"<function_call\b[^>]*>.*?</function_call>",
    r"<invoke\b[^>]*>.*?</invoke>",
    r"<tool\b[^>]*>.*?</tool>",
    r"<parameter\b[^>]*>.*?</parameter>",
)

_ORPHAN_TOOL_OPEN = re.compile(
    r"<(?:tool_call|function_call|invoke|tool|parameter)\b[^>]*>.*?(?=\n\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_agent_report_text(text: str | None) -> str:
    """Remove pseudo-XML tool-call markup that some models emit in plain text."""
    if not text:
        return ""
    cleaned = str(text)
    for pattern in _TOOL_CALL_BLOCKS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = _ORPHAN_TOOL_OPEN.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
