"""Optional HTTP integrations with Vein Signals, Vein Explorer, and Vein Aggregator."""

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
from tradingagents.integrations.vein_aggregator_client import (
    fetch_intelligence_bundle,
    is_vein_aggregator_enabled,
)

__all__ = [
    "analyze_symbol",
    "fetch_intelligence_bundle",
    "fetch_signal_validation",
    "is_golden_trend_enabled",
    "is_vein_aggregator_enabled",
    "normalize_signal_result",
    "pick_primary_result",
    "render_signal_validation_markdown",
    "write_signal_validation_artifacts",
]
