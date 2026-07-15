"""Backward-compatible re-export for the CLI."""

from tradingagents.metrics.callback_handler import ReportMetricsCallbackHandler

StatsCallbackHandler = ReportMetricsCallbackHandler

__all__ = ["StatsCallbackHandler", "ReportMetricsCallbackHandler"]
