"""Intelligence target types for Vein Aggregator requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TargetType = Literal["equity", "commodity", "sector", "index", "crypto"]


@dataclass(frozen=True)
class IntelligenceTarget:
    type: TargetType
    value: str

    def to_payload(self) -> dict[str, str]:
        return {"type": self.type, "value": self.value.strip()}

    @staticmethod
    def from_mapping(raw: dict[str, Any] | None) -> IntelligenceTarget | None:
        if not isinstance(raw, dict):
            return None
        target_type = str(raw.get("type") or "").strip().lower()
        value = str(raw.get("value") or "").strip()
        if not target_type or not value:
            return None
        if target_type not in ("equity", "commodity", "sector", "index", "crypto"):
            return None
        return IntelligenceTarget(type=target_type, value=value)


def resolve_report_subject(*, ticker: str | None, target: IntelligenceTarget | None) -> str:
    """Graph/PDF subject label from ticker or thematic target."""
    if ticker and ticker.strip():
        return ticker.strip().upper()
    if target is not None and target.value.strip():
        return target.value.strip().upper().replace(" ", "_")[:32]
    raise ValueError("ticker or target is required")


def is_equity_like_target(target: IntelligenceTarget | None) -> bool:
    if target is None:
        return True
    return target.type in ("equity", "index", "crypto")


def resolve_asset_type(target: IntelligenceTarget | None) -> str:
    """Graph asset_type: stock, crypto, or thematic (sector/commodity/index)."""
    if target is None:
        return "stock"
    if target.type == "crypto":
        return "crypto"
    if target.type in ("sector", "commodity", "index"):
        return "thematic"
    return "stock"


def build_thematic_instrument_context(
    *,
    subject: str,
    target: IntelligenceTarget,
    primary_symbol: str | None = None,
) -> str:
    """Prompt context for sector, commodity, and index reports."""
    type_label = target.type.replace("_", " ")
    value_label = target.value.replace("_", " ").title()
    proxy = (
        f" Proxy symbol for optional market tools: `{primary_symbol}`."
        if primary_symbol
        else ""
    )
    return (
        f"This run analyzes the {type_label} **{value_label}** (subject `{subject}`). "
        f"It is a thematic intelligence report, not a single-company equity analysis.{proxy} "
        "Treat the Vein Aggregator pre-fetched bundle as primary news and social context. "
        "Do not invent company-specific fundamentals unless explicitly present in the bundle."
    )


def resolve_display_label(
    *,
    subject: str,
    target: IntelligenceTarget | None,
    intelligence_bundle: dict[str, Any] | None = None,
) -> str:
    """Human-readable label for PDF headers and executive summary."""
    if intelligence_bundle:
        from tradingagents.integrations.intelligence_bundle_format import (
            resolve_bundle_subject_label,
        )

        label = resolve_bundle_subject_label(intelligence_bundle, subject)
        if label and label.upper() != subject.upper():
            return label
    if target is not None:
        return f"{target.value.replace('_', ' ').title()} ({target.type})"
    return subject
