import pytest

from tradingagents.agents.utils.report_text import sanitize_agent_report_text

BEAR_WITH_TOOL_CALL = """Bear Analyst: I'll gather the necessary data to build a comprehensive bear case for Sumco Corporation (3436.T). Let
me start by collecting relevant information about the company, its financial performance, and the semiconductor
industry landscape.
<tool_call>
<tool name="ddg-search">
<parameter name="query">Sumco Corporation 3436.T semiconductor silicon wafer company news
2024</parameter>
<parameter name="max results">10</parameter>
</tool>
</tool_call>
The silicon wafer cycle remains weak into 2026."""


@pytest.mark.unit
def test_sanitize_agent_report_text_removes_tool_call_block():
    cleaned = sanitize_agent_report_text(BEAR_WITH_TOOL_CALL)
    assert "<tool_call>" not in cleaned
    assert "<parameter" not in cleaned
    assert "ddg-search" not in cleaned
    assert "Bear Analyst:" in cleaned
    assert "silicon wafer cycle remains weak" in cleaned


@pytest.mark.unit
def test_sanitize_agent_report_text_preserves_plain_text():
    text = "Bull Analyst: Revenue growth remains strong."
    assert sanitize_agent_report_text(text) == text
