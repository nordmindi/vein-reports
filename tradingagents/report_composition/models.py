"""Curated final-report models for publication-safe rendering."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportMode(str, Enum):
    COMPACT = "compact"
    FULL = "full"
    BLOCKED = "blocked"


SECTION_LIMITS: dict[str, dict[str, int]] = {
    "executive_summary": {"max_words": 900},
    "signal_validation": {"max_words": 300},
    "market_summary": {"max_words": 600},
    "fundamentals_summary": {"max_words": 700},
    "news_sentiment_summary": {"max_words": 600},
    "risks": {"max_words": 500},
    "portfolio_synthesis": {"max_words": 600},
}

BLOCKED_FORBIDDEN_TERMS: tuple[str, ...] = (
    "FINAL TRANSACTION PROPOSAL",
    "BUY",
    "SELL",
    "OVERWEIGHT",
    "UNDERWEIGHT",
    "ENTRY",
    "STOP LOSS",
    "TAKE PROFIT",
    "POSITION SIZE",
    "REDUCE EXPOSURE",
    "ADD EXPOSURE",
)

# Longest phrases first. Neutral replacements keep meaning without failing
# RHETORICAL_LANGUAGE validation in published composition.
RHETORICAL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("reading the tea leaves", "interpreting limited signals"),
    ("screaming sell signal", "bearish technical signal"),
    ("deer in the headlights", "hesitant"),
    ("clash violently", "conflict sharply"),
    ("clashes violently", "conflict sharply"),
    ("clashed violently", "conflicted sharply"),
    ("clashing violently", "conflicting sharply"),
    ("extremely compelling", "supportive"),
    ("very compelling", "supportive"),
    ("bull's mirage", "optimistic setup"),
    ("bulls mirage", "optimistic setup"),
    ("massive mistake", "material risk"),
    ("suicidal stop", "aggressive stop"),
    ("smart money", "institutional flows"),
    ("brick wall", "firm resistance"),
    ("slam dunk", "favorable setup"),
    ("can't miss", "notable"),
    ("no-brainer", "straightforward"),
    ("no brainer", "straightforward"),
    ("bulls are in control", "buyers retain control"),
    ("catastrophic", "steep"),
    ("inevitable", "likely"),
    ("guaranteed", "probable"),
    ("gambling", "speculative positioning"),
)

AGENT_PROCESS_PHRASES: tuple[str, ...] = (
    "now i have all data needed",
    "now i have all the data needed",
    "let me analyze the findings",
    "let me compile the comprehensive analysis",
    "let me compile the comprehensive report",
    "let me compile a comprehensive fundamental analysis report",
    "let me compile a comprehensive analysis report",
    "let me compile a comprehensive market structure report",
    "i now have comprehensive data across all financial statements",
    "based on the comprehensive data retrieved",
    "i'll now compile a detailed fundamental analysis report",
)

# Broader patterns for agent meta-language that varies by model/run.
AGENT_PROCESS_REGEXES: tuple[str, ...] = (
    r"\blet me compile\b[^.!?\n]*(?:report|analysis)\b[.!?]?",
    r"\blet me analyze the findings\b[.!?]?",
    r"\bi(?:'ll| will) (?:now )?(?:compile|prepare|draft|write)\b[^.!?\n]*(?:report|analysis)\b[.!?]?",
    r"\bnow i have (?:all )?(?:the )?data\b[^.!?\n]*(?:needed|required|gathered|available)\b[.!?]?",
    r"\bi now have all (?:the )?data\b[^.!?\n]*(?:needed|required|to compile)\b[^.!?\n]*[.!?]?",
    r"\bi now have (?:comprehensive |sufficient )?data\b[^.!?\n]*[.!?]?",
    r"\bbased on (?:the )?(?:comprehensive )?data (?:i(?:'ve| have) |we(?:'ve| have) )?(?:gathered|retrieved)\b[^.!?\n]*[.!?]?",
    r"\bcomprehensive market structure report for\b[^.!?\n]*[.!?]?",
)


ResearchRecommendation = Literal[
    "NO_CURRENT_TRANSACTION",
    "WATCHLIST",
    "TRADE_CANDIDATE",
    "RESEARCH_ONLY",
    "INSUFFICIENT_EVIDENCE",
]


class PortfolioManagerSynthesis(BaseModel):
    recommendation: ResearchRecommendation
    confidence: Literal["low", "medium", "high"]
    action_allowed: bool
    summary: str
    market_view: str = ""
    fundamentals_view: str = ""
    news_sentiment_view: str = ""
    signal_service_view: str | None = None
    key_supportive_points: list[str] = Field(default_factory=list)
    key_caution_points: list[str] = Field(default_factory=list)
    required_confirmations: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)


class FinalReport(BaseModel):
    symbol: str
    company_name: str | None = None
    report_mode: ReportMode
    publication_status: str
    executive_summary: str
    signal_validation: str | None = None
    market_summary: str | None = None
    fundamentals_summary: str | None = None
    news_sentiment_summary: str | None = None
    risk_summary: str | None = None
    portfolio_synthesis: PortfolioManagerSynthesis
    blocking_reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    appendix: str | None = None
