"""Reddit search fetcher for ticker-specific discussion posts.

Default path is Reddit's public Atom/RSS search feed
(``reddit.com/r/{sub}/search.rss``). The richer JSON search endpoint
(``/search.json``) is reliably WAF-blocked (``HTTP 403``) for public clients
(issue #862), and probing it on every call only doubled our request volume
against Reddit's per-IP rate limit — tripping ``429`` on the RSS fallback — so
it is kept (``_fetch_subreddit_json``) but not used by default.

Rate-limit strategy:
- Shared process-wide cooldown after any 429 (honours ``Retry-After``).
- Exponential backoff with multiple retries per subreddit.
- Short TTL response cache so re-runs / duplicate analyst calls do not
  re-hit Reddit within the same window.
- Paced inter-subreddit delay; cooldown is waited before each request.

RSS lacks score / comment counts, so those posts are marked and the formatter
omits the metrics rather than printing fake zeros.

No API key required. Returns formatted plaintext blocks ready for prompt
injection and degrades gracefully — returns a placeholder string rather than
raising, so callers never special-case missing data.
"""

from __future__ import annotations

import html
import http.client
import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_RSS_HOSTS = (
    "https://www.reddit.com",
    "https://old.reddit.com",
)
_RSS_PATH = "/r/{sub}/search.rss?{qs}"
# A descriptive, identified User-Agent (per Reddit's API etiquette). Reddit
# blocks generic/anonymous tokens like bare "Mozilla/5.0" or "curl/…" but
# serves this one on both endpoints; the RSS feed accepts it even when the
# JSON search endpoint 403s, so no browser-spoofing is needed.
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

# Process-wide rate-limit coordination. Reddit's public IP bucket is shared
# across all subreddit fetches in a run; a 429 on one must slow the rest.
_rate_lock = threading.Lock()
_cooldown_until = 0.0
_cache_lock = threading.Lock()
_response_cache: dict[tuple[str, str, int], tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 900.0  # 15 minutes
_MAX_RETRIES = 3
_DEFAULT_BACKOFFS = (5.0, 15.0, 30.0)
_last_fetch_rate_limited = False


def _search_qs(ticker: str, limit: int) -> str:
    return urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
        "limit": limit,
    })


def _iso_to_timestamp(iso_str: str | None) -> float | None:
    """Parse an Atom ``published`` timestamp to a UTC epoch, or None."""
    if not iso_str:
        return None
    try:
        normalized = iso_str[:-1] + "+00:00" if iso_str.endswith("Z") else iso_str
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return None


def _strip_html(content: str) -> str:
    """Reduce the HTML body Reddit embeds in an Atom entry to plain text."""
    if not content:
        return ""
    # Reddit wraps the real selftext between SC_OFF / SC_ON markers.
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->")[1].split("<!-- SC_ON -->")[0]
    text = re.sub(r"<[^>]+>", " ", content)
    return " ".join(html.unescape(text).split())


def _retry_after_seconds(exc: HTTPError) -> float | None:
    """Seconds to wait from a 429's ``Retry-After`` header, capped at 60s."""
    try:
        val = exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None
        return min(float(val), 60.0) if val else None
    except (ValueError, TypeError, AttributeError):
        return None


def _note_rate_limit(wait: float) -> None:
    """Extend the shared cooldown so later subreddit fetches wait too."""
    global _cooldown_until
    with _rate_lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + wait)


def _wait_for_cooldown() -> None:
    with _rate_lock:
        remaining = _cooldown_until - time.monotonic()
    if remaining > 0:
        logger.info("Reddit cooldown: waiting %.1fs before next request", remaining)
        time.sleep(remaining)


def _cache_get(key: tuple[str, str, int]) -> list[dict] | None:
    with _cache_lock:
        entry = _response_cache.get(key)
        if not entry:
            return None
        expires_at, posts = entry
        if time.monotonic() >= expires_at:
            _response_cache.pop(key, None)
            return None
        return [dict(p) for p in posts]


def _cache_set(key: tuple[str, str, int], posts: list[dict]) -> None:
    with _cache_lock:
        _response_cache[key] = (
            time.monotonic() + _CACHE_TTL_SEC,
            [dict(p) for p in posts],
        )


def clear_reddit_cache() -> None:
    """Test helper: drop cached Reddit responses and cooldown."""
    global _cooldown_until, _last_fetch_rate_limited
    with _cache_lock:
        _response_cache.clear()
    with _rate_lock:
        _cooldown_until = 0.0
    _last_fetch_rate_limited = False


def last_fetch_was_rate_limited() -> bool:
    return _last_fetch_rate_limited


def _parse_atom_feed(payload: bytes, limit: int) -> list[dict]:
    root = ET.fromstring(payload)
    posts = []
    for entry in root.findall("atom:entry", _ATOM_NS)[:limit]:
        title_el = entry.find("atom:title", _ATOM_NS)
        published_el = entry.find("atom:published", _ATOM_NS)
        content_el = entry.find("atom:content", _ATOM_NS)
        posts.append({
            "title": (title_el.text if title_el is not None else "") or "",
            "score": None,
            "num_comments": None,
            "created_utc": _iso_to_timestamp(
                published_el.text if published_el is not None else None
            ),
            "selftext": _strip_html(content_el.text if content_el is not None else ""),
            "source": "rss",
        })
    return posts


def _fetch_subreddit_rss(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
    max_retries: int = _MAX_RETRIES,
) -> list[dict]:
    """Default path: parse the public Atom search feed for a subreddit.

    Carries no score / comment counts, so those fields are left None and the
    post is tagged ``source="rss"`` for honest display. On a 429 (Reddit's
    per-IP rate limit) we back off with exponential delays — honouring
    ``Retry-After`` when present — and try an alternate host before giving up.
    """
    global _last_fetch_rate_limited

    cache_key = (ticker.upper(), sub.lower(), limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Reddit RSS cache hit for r/%s · %s", sub, ticker)
        _last_fetch_rate_limited = False
        return cached

    qs = _search_qs(ticker, limit)
    last_error: Exception | None = None
    saw_rate_limit = False

    for host in _RSS_HOSTS:
        url = f"{host}{_RSS_PATH.format(sub=sub, qs=qs)}"
        for attempt in range(max_retries + 1):
            _wait_for_cooldown()
            req = Request(url, headers={"User-Agent": _UA})
            try:
                with urlopen(req, timeout=timeout) as resp:
                    posts = _parse_atom_feed(resp.read(), limit)
                _cache_set(cache_key, posts)
                _last_fetch_rate_limited = False
                return posts
            except HTTPError as exc:
                last_error = exc
                if exc.code != 429:
                    logger.warning(
                        "Reddit RSS fetch failed for r/%s · %s via %s: %s",
                        sub, ticker, host, exc,
                    )
                    break  # try next host
                saw_rate_limit = True
                wait = _retry_after_seconds(exc)
                if wait is None:
                    wait = _DEFAULT_BACKOFFS[min(attempt, len(_DEFAULT_BACKOFFS) - 1)]
                _note_rate_limit(wait)
                if attempt >= max_retries:
                    logger.warning(
                        "Reddit RSS 429 for r/%s · %s via %s — giving up after %d retries",
                        sub, ticker, host, attempt,
                    )
                    break
                logger.warning(
                    "Reddit RSS 429 for r/%s · %s via %s — backing off %.1fs "
                    "(attempt %d/%d)",
                    sub, ticker, host, wait, attempt + 1, max_retries,
                )
                time.sleep(wait)
            except (OSError, http.client.HTTPException, ET.ParseError) as exc:
                last_error = exc
                logger.warning(
                    "Reddit RSS fetch failed for r/%s · %s via %s: %s",
                    sub, ticker, host, exc,
                )
                break

    _last_fetch_rate_limited = saw_rate_limit
    if last_error is not None:
        logger.warning(
            "Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, last_error,
        )
    # Do not cache empties produced after rate limits — retry next call.
    return []


def _fetch_subreddit_json(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Richer JSON search path (carries score / comment counts).

    Reddit's WAF currently returns ``403 Blocked`` on this endpoint for
    non-OAuth clients (issue #862), so it is NOT used by default — calling it on
    every request only doubled our volume against the per-IP rate limit and
    triggered 429s on the RSS fallback. Kept for the day the WAF relaxes or an
    OAuth token is wired in; degrades to RSS on failure.
    """
    url = _API.format(sub=sub, qs=_search_qs(ticker, limit))
    _wait_for_cooldown()
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
        children = (payload.get("data") or {}).get("children") or []
        return [c.get("data", {}) for c in children if isinstance(c, dict)]
    except HTTPError as exc:
        if exc.code == 429:
            wait = _retry_after_seconds(exc) or 15.0
            _note_rate_limit(wait)
        logger.warning(
            "Reddit JSON fetch failed for r/%s · %s: %s — falling back to RSS feed.",
            sub, ticker, exc,
        )
        return _fetch_subreddit_rss(ticker, sub, limit, timeout)
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        logger.warning(
            "Reddit JSON fetch failed for r/%s · %s: %s — falling back to RSS feed.",
            sub, ticker, exc,
        )
        return _fetch_subreddit_rss(ticker, sub, limit, timeout)


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Fetch one subreddit, RSS-first.

    The JSON search endpoint is reliably WAF-blocked (403) for public clients,
    so we go straight to the RSS feed — which serves our identified User-Agent
    reliably — halving our request volume against Reddit's per-IP rate limit.
    """
    return _fetch_subreddit_rss(ticker, sub, limit, timeout)


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    inter_request_delay: float = 2.5,
) -> str:
    """Fetch recent Reddit posts mentioning ``ticker`` across finance
    subreddits and return them as a formatted plaintext block.

    ``inter_request_delay`` paces the (now RSS-only) per-subreddit requests to
    stay under Reddit's public per-IP rate limit; combined with shared cooldown
    and caching it makes 429s rare even when several analyses run back-to-back.
    """
    blocks = []
    total_posts = 0
    rate_limited_subs: list[str] = []
    sub_list = list(subreddits)

    for i, sub in enumerate(sub_list):
        if i > 0:
            time.sleep(inter_request_delay)
        posts = _fetch_subreddit(ticker, sub, limit_per_sub, timeout)
        if not posts:
            if last_fetch_was_rate_limited():
                rate_limited_subs.append(sub)
                blocks.append(
                    f"r/{sub}: <temporarily unavailable due to Reddit rate limiting; "
                    f"retry later>"
                )
            else:
                blocks.append(
                    f"r/{sub}: <no posts found mentioning {ticker.upper()} "
                    f"in the past 7 days>"
                )
            continue

        total_posts += len(posts)
        via_rss = any(p.get("source") == "rss" for p in posts)
        header = f"r/{sub} — {len(posts)} recent posts mentioning {ticker.upper()}"
        header += " (via RSS feed; scores/comments unavailable):" if via_rss else ":"
        lines = [header]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score")
            comments = p.get("num_comments")
            created = p.get("created_utc")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            )
            # Score / comment counts are absent on the RSS fallback path —
            # show them only when present rather than printing fake zeros.
            meta = created_str
            if score is not None and comments is not None:
                meta += f" · {score:>4}↑ · {comments:>3}c"
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{meta}] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        if rate_limited_subs:
            return (
                f"<Reddit temporarily rate-limited for {ticker.upper()} on "
                f"{', '.join(f'r/{s}' for s in rate_limited_subs)}; "
                f"sentiment should rely on other sources this run>"
            )
        return (
            f"<no Reddit posts found mentioning {ticker.upper()} across "
            f"{', '.join(f'r/{s}' for s in sub_list)} in the past 7 days>"
        )
    return "\n\n".join(blocks)
