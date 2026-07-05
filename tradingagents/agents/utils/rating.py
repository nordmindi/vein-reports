"""Shared rating vocabulary and a deterministic heuristic parser.

- The same directional scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)
- Insufficient Evidence is the safe non-transaction outcome when validation
  fails or evidence is incomplete.

Centralising it here avoids drift between those call sites.
"""

from __future__ import annotations

import re

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)
SAFE_RATING = "Insufficient Evidence"
RATINGS: Tuple[str, ...] = RATINGS_5_TIER + (SAFE_RATING,)

_RATING_CANONICAL = {r.lower(): r for r in RATINGS}
_RATING_CANONICAL["insufficient_evidence"] = SAFE_RATING
_RATING_CANONICAL["insufficient-evidence"] = SAFE_RATING

# Matches "Rating: X" / "rating - X" / "Rating: **X**" — tolerates markdown
# bold wrappers and either a colon or hyphen separator.
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*([A-Za-z_\-\s]+)", re.IGNORECASE)


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a canonical rating from prose text.

    Two-pass strategy:
    1. Look for an explicit "Rating: X" label (tolerant of markdown bold).
    2. Fall back to the first 5-tier rating word found anywhere in the text.

    Returns a Title-cased rating string, or ``default`` if no rating word appears.
    """
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


def _canonical_rating(value: str) -> str | None:
    clean = value.strip("*:., \t\r\n")
    clean = re.sub(r"\s+", " ", clean)
    for rating in RATINGS:
        if clean.lower().startswith(rating.lower()):
            return rating
    return _RATING_CANONICAL.get(clean.lower())
