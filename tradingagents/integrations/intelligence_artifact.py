"""Markdown and artifact writers for Vein Aggregator intelligence provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _retrieval_summary(bundle: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        return {"status": "missing"}
    retrieval = bundle.get("retrieval") if isinstance(bundle.get("retrieval"), dict) else {}
    sections = retrieval.get("sections") if isinstance(retrieval.get("sections"), dict) else {}
    return {
        "status": retrieval.get("status") or "unknown",
        "warnings": list(retrieval.get("warnings") or [])[:20],
        "sections": {
            name: {
                "status": (meta or {}).get("status") if isinstance(meta, dict) else None,
                "item_count": (meta or {}).get("item_count") if isinstance(meta, dict) else None,
            }
            for name, meta in sections.items()
        },
    }


def render_intelligence_markdown(
    bundle: dict[str, Any] | None,
    briefs: dict[str, Any] | None = None,
) -> str:
    summary = _retrieval_summary(bundle)
    lines = [
        "## Vein Aggregator Intelligence",
        "",
        f"- **Retrieval status:** {summary.get('status', 'missing')}",
        f"- **Primary symbol:** {(bundle or {}).get('primary_symbol') if bundle else 'n/a'}",
        "",
    ]
    sections = summary.get("sections") or {}
    if sections:
        lines.append("**Sections:**")
        for name, meta in sections.items():
            lines.append(
                f"- {name}: {meta.get('status') or 'unknown'}"
                + (f" ({meta.get('item_count')} items)" if meta.get("item_count") is not None else "")
            )
        lines.append("")

    warnings = summary.get("warnings") or []
    if warnings:
        lines.append("**Warnings:**")
        for warning in warnings[:12]:
            lines.append(f"- {warning}")
        lines.append("")

    if isinstance(briefs, dict) and briefs:
        sentiment = briefs.get("sentiment") if isinstance(briefs.get("sentiment"), dict) else {}
        news = briefs.get("news") if isinstance(briefs.get("news"), dict) else {}
        if sentiment or news:
            lines.append("**Briefs:**")
            if sentiment.get("headline"):
                lines.append(f"- Sentiment: {sentiment.get('headline')}")
            if news.get("headline_sentiment_band"):
                lines.append(f"- News band: {news.get('headline_sentiment_band')}")
            lines.append("")

    if summary.get("status") in {"partial", "empty", "missing"}:
        lines.extend(
            [
                "**Report impact:**",
                "Aggregator coverage was incomplete or unavailable. Treat news/social context as "
                "partial and prefer fail-soft interpretation.",
                "",
            ]
        )

    return "\n".join(lines)


def write_intelligence_artifacts(
    save_path: Path,
    bundle: dict[str, Any] | None,
    briefs: dict[str, Any] | None = None,
) -> Path | None:
    if not bundle and not briefs:
        return None
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "intelligence_bundle": bundle,
        "briefs": briefs,
        "retrieval": _retrieval_summary(bundle),
    }
    json_path = save_path / "intelligence_bundle.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path = save_path / "intelligence_bundle.md"
    md_path.write_text(render_intelligence_markdown(bundle, briefs), encoding="utf-8")
    return md_path
