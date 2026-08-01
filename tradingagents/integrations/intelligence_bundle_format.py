"""Format vein-intelligence-v1 bundles for analyst prompt injection."""

from __future__ import annotations

from typing import Any


def has_intelligence_bundle(state_or_config: dict[str, Any]) -> bool:
    bundle = state_or_config.get("vein_intelligence_bundle")
    return isinstance(bundle, dict) and bool(bundle.get("version"))


def section_status(bundle: dict[str, Any], section: str) -> str:
    retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}
    sections = retrieval.get("sections") if isinstance(retrieval.get("sections"), dict) else {}
    meta = sections.get(section) if isinstance(sections.get(section), dict) else {}
    if not meta:
        return "ok"
    return str(meta.get("status") or "empty")


def section_status_value(bundle: dict[str, Any], section: str) -> int:
    retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}
    sections = retrieval.get("sections") if isinstance(retrieval.get("sections"), dict) else {}
    meta = sections.get(section) if isinstance(sections.get(section), dict) else {}
    if not isinstance(meta, dict):
        return 0
    return int(meta.get("item_count") or 0)


def retrieval_warnings(bundle: dict[str, Any]) -> list[str]:
    retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}
    return [str(w) for w in (retrieval.get("warnings") or [])]


def _reddit_rate_limited(bundle: dict[str, Any]) -> bool:
    retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}
    sections = retrieval.get("sections") if isinstance(retrieval.get("sections"), dict) else {}
    social = sections.get("social") if isinstance(sections.get("social"), dict) else {}
    for warning in list(social.get("warnings") or []) + list(retrieval.get("warnings") or []):
        text = str(warning).lower()
        if "reddit" in text and ("429" in text or "rate" in text):
            return True
    social_data = bundle.get("social") if isinstance(bundle.get("social"), dict) else {}
    reddit_summary = str(social_data.get("reddit_summary") or "").lower()
    return "rate-limited" in reddit_summary or "rate limiting" in reddit_summary


def format_retrieval_quality_note(bundle: dict[str, Any]) -> str:
    retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}
    status = retrieval.get("status") or "unknown"
    warnings = retrieval_warnings(bundle)
    parts = [f"Retrieval status: {status}."]
    if warnings:
        parts.append("Warnings: " + "; ".join(warnings))
    sections = retrieval.get("sections") if isinstance(retrieval.get("sections"), dict) else {}
    if sections:
        section_bits = []
        for name, meta in sections.items():
            if isinstance(meta, dict):
                section_bits.append(
                    f"{name}={meta.get('status', '?')} ({meta.get('item_count', 0)} items)"
                )
        if section_bits:
            parts.append("Sections: " + ", ".join(section_bits))
    return " ".join(parts)


def format_sentiment_brief_header(briefs: dict[str, Any] | None) -> str:
    if not isinstance(briefs, dict):
        return ""
    sentiment = briefs.get("sentiment") if isinstance(briefs.get("sentiment"), dict) else {}
    if not sentiment:
        return ""
    band = sentiment.get("overall_band") or "Neutral"
    score = sentiment.get("overall_score", 5.0)
    confidence = sentiment.get("confidence") or "low"
    narrative = sentiment.get("narrative") or ""
    lines = [
        f"**Vein Aggregator sentiment brief** (non-authoritative): "
        f"{band} (score {score}/10, confidence {confidence})",
    ]
    if narrative:
        lines.append(str(narrative))
    return "\n".join(lines)


def format_news_headline_sentiment(briefs: dict[str, Any] | None) -> str:
    if not isinstance(briefs, dict):
        return ""
    news = briefs.get("news") if isinstance(briefs.get("news"), dict) else {}
    if not news:
        return ""
    band = news.get("headline_sentiment_band")
    score = news.get("headline_sentiment_score")
    if not band and score is None:
        return ""
    score_text = f", score {score:.2f}" if score is not None else ""
    articles = news.get("articles_with_sentiment")
    articles_text = f" ({articles} articles scored)" if articles else ""
    return f"**Headline sentiment** (vendor-scored): {band}{score_text}{articles_text}"


def _format_news_articles(
    articles: list[dict],
    *,
    header: str,
) -> str:
    if not articles:
        return f"{header}\n\n<no articles>"
    lines = [header, ""]
    for article in articles:
        title = article.get("title") or "Untitled"
        source = article.get("source") or "Unknown"
        lines.append(f"### {title} (source: {source})")
        sentiment_label = article.get("sentiment_label")
        sentiment_score = article.get("sentiment_score")
        if sentiment_label or sentiment_score is not None:
            label = sentiment_label or "?"
            score_part = f" ({sentiment_score:+.2f})" if sentiment_score is not None else ""
            lines.append(f"Sentiment: {label}{score_part}")
        summary = article.get("summary") or ""
        if summary:
            lines.append(str(summary))
        url = article.get("url") or ""
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    return "\n".join(lines).strip()


def resolve_bundle_subject_label(bundle: dict[str, Any], fallback: str) -> str:
    """Display label from bundle target metadata or primary proxy symbol."""
    target = bundle.get("target")
    if isinstance(target, dict):
        value = str(target.get("value") or "").strip()
        target_type = str(target.get("type") or "").strip()
        if value and target_type and target_type not in ("equity",):
            return f"{value} ({target_type})"
        if value:
            return value.upper()

    retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}
    news_retrieval = (
        retrieval.get("news_retrieval")
        if isinstance(retrieval.get("news_retrieval"), dict)
        else {}
    )
    target_label = news_retrieval.get("target_label")
    if target_label:
        return str(target_label)

    primary = bundle.get("primary_symbol")
    if primary:
        return str(primary).upper()
    return fallback


def format_news_block(bundle: dict[str, Any], ticker: str) -> str:
    subject = resolve_bundle_subject_label(bundle, ticker)
    if section_status(bundle, "news") == "empty":
        return f"## {subject} News (Vein Aggregator)\n\n<no news data collected>"

    news = bundle.get("news") if isinstance(bundle.get("news"), dict) else {}
    primary = news.get("primary") or []
    window = bundle.get("window") or {}
    start = window.get("start") or "?"
    end = window.get("end") or "?"
    header = f"## {subject} News (Vein Aggregator), from {start} to {end}:"
    parts = [_format_news_articles(primary, header=header)]
    peers = news.get("peers") or []
    for group in peers:
        if not isinstance(group, dict):
            continue
        peer = group.get("symbol") or "PEER"
        peer_articles = group.get("articles") or []
        if peer_articles:
            parts.append(
                _format_news_articles(
                    peer_articles,
                    header=f"## Peer news ({peer}) supplemental:",
                )
            )
    return "\n\n".join(parts)


def format_stocktwits_block(bundle: dict[str, Any]) -> str:
    if section_status(bundle, "social") == "empty":
        return "<no social data collected>"

    social = bundle.get("social") if isinstance(bundle.get("social"), dict) else {}
    summary = social.get("stocktwits_summary") or ""
    if summary:
        return summary
    messages = social.get("stocktwits") or []
    if not messages:
        return "<no StockTwits messages in intelligence bundle>"
    lines = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        tag = msg.get("sentiment_tag") or "no-label"
        lines.append(
            f"[{msg.get('created_at', '')} · @{msg.get('user', '?')} · {tag}] "
            f"{msg.get('body', '')}"
        )
    return "\n".join(lines)


def format_reddit_block(bundle: dict[str, Any]) -> str:
    if section_status(bundle, "social") == "empty":
        return "<no social data collected>"
    if _reddit_rate_limited(bundle):
        return "<Reddit omitted due to rate limiting; use StockTwits summary above>"

    social = bundle.get("social") if isinstance(bundle.get("social"), dict) else {}
    summary = social.get("reddit_summary") or ""
    if summary:
        return summary
    posts = social.get("reddit") or []
    if not posts:
        return "<no Reddit posts in intelligence bundle>"
    lines = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        sub = post.get("subreddit") or "?"
        lines.append(f"r/{sub}: {post.get('title', '')}")
    return "\n".join(lines)


def format_news_analyst_context(
    bundle: dict[str, Any],
    ticker: str,
    *,
    briefs: dict[str, Any] | None = None,
) -> str:
    """Macro, global news, and prediction markets for the News Analyst."""
    sections: list[str] = [
        "The following intelligence was pre-fetched by Vein Aggregator. "
        "Use it as primary context; call tools only if you need additional detail.",
    ]
    quality = format_retrieval_quality_note(bundle)
    if quality:
        sections.append(quality)
    headline_sentiment = format_news_headline_sentiment(briefs)
    if headline_sentiment:
        sections.append(headline_sentiment)

    news = bundle.get("news") if isinstance(bundle.get("news"), dict) else {}
    if section_status(bundle, "news") != "empty":
        global_articles = news.get("global") or []
        if global_articles:
            window = bundle.get("window") or {}
            sections.append(
                _format_news_articles(
                    global_articles,
                    header=(
                        f"## Global Market News, from {window.get('start', '?')} "
                        f"to {window.get('end', '?')}:"
                    ),
                )
            )
        sections.append(format_news_block(bundle, ticker))
    else:
        sections.append("<no news data collected in intelligence bundle>")

    if section_status(bundle, "macro") != "empty":
        macro = bundle.get("macro") if isinstance(bundle.get("macro"), dict) else {}
        for indicator in macro.get("indicators") or []:
            if not isinstance(indicator, dict):
                continue
            markdown = indicator.get("markdown") or ""
            if markdown:
                sections.append(markdown)

    if section_status(bundle, "prediction_markets") != "empty":
        pm = (
            bundle.get("prediction_markets")
            if isinstance(bundle.get("prediction_markets"), dict)
            else {}
        )
        markets = pm.get("markets") or []
        if markets:
            topic = pm.get("topic") or "macro and financial markets"
            lines = [f'## Polymarket prediction markets: "{topic}"', ""]
            for market in markets:
                if not isinstance(market, dict):
                    continue
                prob = market.get("probability", 0)
                lines.append(
                    f"- **{market.get('question', '')}** — "
                    f"{market.get('outcome_label', 'Yes')} {prob:.0%}"
                )
            sections.append("\n".join(lines))

    return "\n\n".join(sections)
