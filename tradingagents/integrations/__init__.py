"""Optional HTTP integrations with Vein Signals and Vein Explorer."""

from tradingagents.integrations.golden_trend_client import (
    analyze_symbol,
    fetch_signal_validation,
    is_golden_trend_enabled,
    normalize_signal_result,
    pick_primary_result,
)
from tradingagents.integrations.signal_validation_section import (
    render_signal_validation_markdown,
    write_signal_validation_artifacts,
)

__all__ = [
    "analyze_symbol",
    "fetch_signal_validation",
    "is_golden_trend_enabled",
    "normalize_signal_result",
    "pick_primary_result",
    "render_signal_validation_markdown",
    "write_signal_validation_artifacts",
]
