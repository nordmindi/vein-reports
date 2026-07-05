"""Markdown and artifact writers for Vein Signals validation in reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_signal_validation_markdown(signal: dict[str, Any]) -> str:
    if not signal:
        return ""

    lines = [
        "## Vein Signals Validation",
        "",
        f"- **Raw signal:** {signal.get('rawSignal', 'NO_SIGNAL')}",
        f"- **Vein Signals final:** {signal.get('signalServiceFinal', signal.get('finalSignal', 'NO_SIGNAL'))}",
        f"- **Combined decision:** {signal.get('finalSignal', 'NO_SIGNAL')}",
        f"- **Trade allowed:** {signal.get('tradeAllowed', False)}",
        f"- **Confidence:** {signal.get('confidenceScore', 0)} / {signal.get('confidenceGrade', 'F')}",
        "",
    ]

    blockers = list(signal.get("hardBlocks") or []) + list(signal.get("flags") or [])[:8]
    if blockers:
        lines.append("**Why not tradable:**")
        for item in blockers[:12]:
            lines.append(f"- {item}")
        lines.append("")

    watchlist = signal.get("watchlistConditions") or []
    if watchlist:
        lines.append("**Watchlist conditions:**")
        for condition in watchlist[:8]:
            if not isinstance(condition, dict):
                continue
            status = condition.get("status") or "unknown"
            label = condition.get("condition") or condition.get("type") or "condition"
            lines.append(f"- [{status}] {label}")
        lines.append("")

    if signal.get("blocksTradePublication"):
        lines.extend(
            [
                "**Report impact:**",
                "This report must not present an active trade candidate while Vein Signals "
                "blocks execution or keeps the setup on the watchlist only.",
                "",
            ]
        )

    return "\n".join(lines)


def write_signal_validation_artifacts(save_path: Path, signal: dict[str, Any]) -> Path | None:
    if not signal:
        return None
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    json_path = save_path / "signal_validation.json"
    json_path.write_text(json.dumps(signal, indent=2, default=str), encoding="utf-8")
    md_path = save_path / "signal_validation.md"
    md_path.write_text(render_signal_validation_markdown(signal), encoding="utf-8")
    return md_path
