"""Report validation helpers for publication gating."""

from .build_technical_validation import attach_technical_validation, build_technical_validation
from .claims import DownstreamClaim, extract_downstream_claims, rejected_claims, verified_claims
from .dashboard import DashboardModel, build_dashboard_model, validate_dashboard_consistency
from .evidence import (
    DecisionEvidenceBundle,
    HistoricalLesson,
    build_decision_evidence_bundle,
    lesson_is_usable,
    usable_historical_lessons,
)
from .instrument import InstrumentRecord, InstrumentResolution, resolve_instrument
from .market_data import MarketDataFreshness, check_market_data_freshness
from .models import ValidationIssue, ValidationResult
from .news import NewsRetrievalStatusRecord, check_news_retrieval
from .report_validator import validate_final_state
from .technical import (
    bearish_divergence,
    bollinger_squeeze_valid,
    bullish_divergence,
    detect_cross,
    macd_components_reconcile,
    validate_technical_claims,
)

__all__ = [
    "InstrumentRecord",
    "InstrumentResolution",
    "MarketDataFreshness",
    "NewsRetrievalStatusRecord",
    "DashboardModel",
    "DecisionEvidenceBundle",
    "DownstreamClaim",
    "HistoricalLesson",
    "ValidationIssue",
    "ValidationResult",
    "attach_technical_validation",
    "bearish_divergence",
    "bollinger_squeeze_valid",
    "build_dashboard_model",
    "build_decision_evidence_bundle",
    "build_technical_validation",
    "bullish_divergence",
    "check_market_data_freshness",
    "check_news_retrieval",
    "detect_cross",
    "extract_downstream_claims",
    "lesson_is_usable",
    "macd_components_reconcile",
    "rejected_claims",
    "resolve_instrument",
    "usable_historical_lessons",
    "validate_technical_claims",
    "validate_dashboard_consistency",
    "validate_final_state",
    "verified_claims",
]
