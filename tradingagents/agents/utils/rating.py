"""Shared rating vocabulary and a deterministic heuristic parser.

- The same directional scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager and Trader (directional context)
- The signal processor (legacy rating extraction)
- The Portfolio Manager now publishes research recommendations instead of buy/sell ratings.
- Insufficient Evidence is the safe non-transaction outcome when validation fails.
"""

from __future__ import annotations

import re

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)
SAFE_RATING = "Insufficient Evidence"
RATINGS: tuple[str, ...] = RATINGS_5_TIER + (SAFE_RATING,)

RESEARCH_RECOMMENDATIONS: tuple[str, ...] = (
    "No current transaction",
    "Watchlist",
    "Trade candidate",
    "Research only",
    "Insufficient evidence",
)

_RATING_CANONICAL = {r.lower(): r for r in RATINGS}
_RATING_CANONICAL["insufficient_evidence"] = SAFE_RATING
_RATING_CANONICAL["insufficient-evidence"] = SAFE_RATING

_RESEARCH_CANONICAL = {r.lower(): r for r in RESEARCH_RECOMMENDATIONS}

# Matches "Rating: X" / "Recommendation: X" — tolerates markdown bold wrappers.
_RATING_LABEL_RE = re.compile(
    r"(?:rating|recommendation).*?[:\-][\s*]*([A-Za-z_\-\s]+)",
    re.IGNORECASE,
)


def parse_research_recommendation(text: str, default: str = "Insufficient evidence") -> str:
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and "recommendation" in line.lower():
            rec = _canonical_research(m.group(1))
            if rec is not None:
                return rec
    for rec in RESEARCH_RECOMMENDATIONS:
        if re.search(rf"\b{re.escape(rec)}\b", text, flags=re.IGNORECASE):
            return rec
    return default


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a canonical rating from prose text."""
    research = parse_research_recommendation(text, default="")
    if research:
        return _research_to_legacy_rating(research)

    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m:
            rating = _canonical_rating(m.group(1))
            if rating is not None:
                return rating

    for line in text.splitlines():
        lower_line = line.lower()
        for rating in RATINGS:
            if re.search(rf"\b{re.escape(rating.lower())}\b", lower_line):
                return rating
        for word in lower_line.split():
            rating = _canonical_rating(word)
            if rating is not None:
                return rating

    return default


def _research_to_legacy_rating(research: str) -> str:
    mapping = {
        "Trade candidate": "Buy",
        "Watchlist": "Hold",
        "No current transaction": "Hold",
        "Research only": "Hold",
        "Insufficient evidence": SAFE_RATING,
    }
    return mapping.get(research, "Hold")


def _canonical_research(value: str) -> str | None:
    clean = value.strip("*:., \t\r\n")
    clean = re.sub(r"\s+", " ", clean)
    for rec in RESEARCH_RECOMMENDATIONS:
        if clean.lower().startswith(rec.lower()):
            return rec
    return _RESEARCH_CANONICAL.get(clean.lower())


def _canonical_rating(value: str) -> str | None:
    clean = value.strip("*:., \t\r\n")
    clean = re.sub(r"\s+", " ", clean)
    for rating in RATINGS:
        if clean.lower().startswith(rating.lower()):
            return rating
    return _RATING_CANONICAL.get(clean.lower())
