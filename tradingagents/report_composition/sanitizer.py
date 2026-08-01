"""Sanitize agent prose and scan blocked reports for forbidden language."""

from __future__ import annotations

import re

from tradingagents.report_composition.models import (
    AGENT_PROCESS_PHRASES,
    AGENT_PROCESS_REGEXES,
    BLOCKED_FORBIDDEN_TERMS,
    RHETORICAL_REPLACEMENTS,
)

_COMPILED_AGENT_REGEXES = tuple(
    re.compile(pattern, flags=re.IGNORECASE) for pattern in AGENT_PROCESS_REGEXES
)

_AGENT_PROCESS_ONLY_RE = re.compile(
    r"^(?:[\s.!?,:;]*)(?:"
    r"let me (?:compile|prepare|draft|write|analyze|review)|"
    r"i(?:'ll| will) (?:now )?(?:compile|prepare|draft|write)|"
    r"now i have (?:all )?(?:the )?data|"
    r"i now have all (?:the )?data|"
    r"i now have (?:comprehensive |sufficient )?data|"
    r"based on (?:the )?(?:comprehensive )?data (?:i(?:'ve| have) |we(?:'ve| have) )?(?:gathered|retrieved)"
    r")\b",
    flags=re.IGNORECASE,
)

_PROCESS_MARKERS = (
    "let me analyze the findings",
    "let me compile",
    "i now have all the data",
    "now i have all the data",
    "based on the comprehensive data retrieved",
)

_COMPILED_RHETORIC = tuple(
    (
        re.compile(rf"\b{re.escape(src)}\b", flags=re.IGNORECASE),
        replacement,
    )
    for src, replacement in RHETORICAL_REPLACEMENTS
)

# Longer phrases first so "FINAL TRANSACTION PROPOSAL" wins over "SELL".
_SORTED_FORBIDDEN_TERMS = tuple(
    sorted(BLOCKED_FORBIDDEN_TERMS, key=len, reverse=True)
)


_SECTION_HEADER_LINE_RE = re.compile(
    r"^#{1,6}\s+(?:"
    r"Portfolio Manager Synthesis|Research Synthesis|Vein Signals Validation|"
    r"Executive Summary|Investment Thesis|Summary of (?:Positions|Analyst Debate)|"
    r".*Market Structure Brief|Fundamental Analysis Report|Company Overview"
    r")[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

_AGENT_ROLE_PREFIX_RE = re.compile(
    r"^(?:Aggressive|Conservative|Neutral|Bull|Bear|Research Manager|Portfolio Manager)\s+"
    r"(?:Analyst|Researcher|Debator|Manager):\s*",
    re.IGNORECASE | re.MULTILINE,
)


def strip_section_headers(text: str) -> str:
    if not text:
        return ""
    cleaned = _SECTION_HEADER_LINE_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_agent_role_prefixes(text: str) -> str:
    if not text:
        return ""
    cleaned = _AGENT_ROLE_PREFIX_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_section_header_only(text: str) -> bool:
    block = text.strip()
    if not block:
        return True
    if re.fullmatch(r"#{1,6}\s+.+", block) and len(block.split()) <= 12:
        return True
    normalized = re.sub(r"^#{1,6}\s+", "", block).strip()
    lowered = normalized.lower()
    return (
        lowered.startswith(
            (
                "portfolio manager synthesis",
                "research synthesis",
                "vein signals validation",
            )
        )
        and len(normalized.split()) <= 12
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


def clean_publication_excerpt(text: str) -> str:
    cleaned = strip_agent_process_phrases(text)
    cleaned = strip_section_headers(cleaned)
    cleaned = strip_agent_role_prefixes(cleaned)
    return cleaned.strip()


def is_agent_process_paragraph(text: str) -> bool:
    """True when a block is only agent preamble, not report content."""
    block = text.strip()
    if not block:
        return True
    if _AGENT_PROCESS_ONLY_RE.match(block):
        return True
    stripped = strip_agent_process_phrases(block)
    if not stripped:
        return True
    if len(stripped.split()) < 8:
        return True
    lowered = block.lower()
    return any(marker in lowered for marker in _PROCESS_MARKERS) and len(
        stripped.split()
    ) < max(8, len(block.split()) // 2)


def soften_rhetorical_language(text: str) -> str:
    """Replace prohibited rhetorical phrases with neutral equivalents."""
    if not text:
        return ""
    softened = text
    for pattern, replacement in _COMPILED_RHETORIC:
        softened = pattern.sub(replacement, softened)
    return softened


def redact_forbidden_transaction_language(text: str) -> str:
    """Redact transaction terms using word boundaries for single-token terms.

    Word boundaries avoid mangling ordinary prose such as ``selling`` →
    ``[redacted]ing`` when ``SELL`` is forbidden.
    """
    if not text:
        return ""
    redacted = text
    for term in _SORTED_FORBIDDEN_TERMS:
        if " " in term:
            redacted = re.sub(re.escape(term), "[redacted]", redacted, flags=re.IGNORECASE)
        else:
            redacted = re.sub(
                rf"\b{re.escape(term)}\b",
                "[redacted]",
                redacted,
                flags=re.IGNORECASE,
            )
    return redacted


def sanitize_for_publication(text: str) -> str:
    from tradingagents.agents.utils.report_text import sanitize_agent_report_text

    cleaned = sanitize_agent_report_text(text)
    cleaned = clean_publication_excerpt(cleaned)
    return soften_rhetorical_language(cleaned)


def scan_blocked_report_text(text: str) -> list[str]:
    violations: list[str] = []
    lowered = text.lower()
    for term in BLOCKED_FORBIDDEN_TERMS:
        if " " in term:
            if term.lower() in lowered:
                violations.append(term)
            continue
        if re.search(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE):
            violations.append(term)
    return violations


def truncate_words(text: str, max_words: int) -> str:
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(".,;:") + "…"
