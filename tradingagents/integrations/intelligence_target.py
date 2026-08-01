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
