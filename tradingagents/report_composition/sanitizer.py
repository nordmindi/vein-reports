"""Sanitize agent prose and scan blocked reports for forbidden language."""

from __future__ import annotations

import re

from tradingagents.report_composition.models import (
    AGENT_PROCESS_PHRASES,
    AGENT_PROCESS_REGEXES,
    BLOCKED_FORBIDDEN_TERMS,
)

_COMPILED_AGENT_REGEXES = tuple(
    re.compile(pattern, flags=re.IGNORECASE) for pattern in AGENT_PROCESS_REGEXES
)

_AGENT_PROCESS_ONLY_RE = re.compile(
    r"^(?:[\s.!?,:;]*)(?:"
    r"let me (?:compile|prepare|draft|write|analyze|review)|"
    r"i(?:'ll| will) (?:now )?(?:compile|prepare|draft|write)|"
    r"now i have (?:all )?(?:the )?data|"
    r"i now have (?:comprehensive |sufficient )?data|"
    r"based on (?:the )?data (?:i(?:'ve| have) |we(?:'ve| have) )gathered"
    r")\b",
    flags=re.IGNORECASE,
)


def strip_agent_process_phrases(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    for phrase in AGENT_PROCESS_PHRASES:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)
    for pattern in _COMPILED_AGENT_REGEXES:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"^\s*[.!?,:;]+\s*", "", cleaned)
    cleaned = re.sub(r"^\s*[.!?,:;]+\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    if not cleaned or re.fullmatch(r"[.\s!?,:;]+", cleaned):
        return ""
    return cleaned


def is_agent_process_paragraph(text: str) -> bool:
    """True when a block is only agent preamble, not report content."""
    block = text.strip()
    if not block:
        return True
    if _AGENT_PROCESS_ONLY_RE.match(block):
        return True
    stripped = strip_agent_process_phrases(block)
    return not stripped or len(stripped.split()) < 8


def redact_forbidden_transaction_language(text: str) -> str:
    if not text:
        return ""
    redacted = text
    for term in BLOCKED_FORBIDDEN_TERMS:
        redacted = re.sub(re.escape(term), "[redacted]", redacted, flags=re.IGNORECASE)
    return redacted


def sanitize_for_publication(text: str) -> str:
    from tradingagents.agents.utils.report_text import sanitize_agent_report_text

    return strip_agent_process_phrases(sanitize_agent_report_text(text))


def scan_blocked_report_text(text: str) -> list[str]:
    violations: list[str] = []
    lowered = text.lower()
    for term in BLOCKED_FORBIDDEN_TERMS:
        if term.lower() in lowered:
            violations.append(term)
    return violations


def truncate_words(text: str, max_words: int) -> str:
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(".,;:") + "…"
