"""Specialist analysts must not be prompted to emit transaction proposals."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tradingagents.agents.utils.agent_utils import (
    get_neutral_debate_language_instruction,
    get_non_authoritative_analyst_instruction,
)

REPO = Path(__file__).resolve().parents[1]
ANALYST_FILES = (
    "tradingagents/agents/analysts/market_analyst.py",
    "tradingagents/agents/analysts/news_analyst.py",
    "tradingagents/agents/analysts/fundamentals_analyst.py",
    "tradingagents/agents/analysts/sentiment_analyst.py",
)
RISK_FILES = (
    "tradingagents/agents/risk_mgmt/conservative_debator.py",
    "tradingagents/agents/risk_mgmt/aggressive_debator.py",
    "tradingagents/agents/risk_mgmt/neutral_debator.py",
)


@pytest.mark.unit
def test_non_authoritative_instruction_bans_transaction_language():
    text = get_non_authoritative_analyst_instruction("fundamentals brief")
    assert "FINAL TRANSACTION PROPOSAL" in text
    assert "Portfolio Manager" in text
    assert "guaranteed" in text


@pytest.mark.unit
def test_debate_instruction_bans_rhetoric_and_transaction_lines():
    text = get_neutral_debate_language_instruction()
    assert "guaranteed" in text
    assert "FINAL TRANSACTION PROPOSAL" in text


@pytest.mark.unit
@pytest.mark.parametrize("rel_path", ANALYST_FILES)
def test_specialist_analysts_do_not_prompt_final_transaction_prefix(rel_path: str):
    source = (REPO / rel_path).read_text(encoding="utf-8")
    assert 'prefix your response with FINAL TRANSACTION PROPOSAL' not in source
    # Keep the ban instruction present (via helper or inline).
    assert (
        "get_non_authoritative_analyst_instruction" in source
        or "FINAL TRANSACTION PROPOSAL — this is" in source
    )


@pytest.mark.unit
@pytest.mark.parametrize("rel_path", RISK_FILES)
def test_risk_debators_require_neutral_language_instruction(rel_path: str):
    source = (REPO / rel_path).read_text(encoding="utf-8")
    assert "get_neutral_debate_language_instruction" in source
    # Ensure the module still parses after edits.
    ast.parse(source)
