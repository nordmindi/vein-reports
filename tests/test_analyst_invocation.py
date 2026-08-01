from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.agents.utils.analyst_invocation import (
    invoke_analyst_with_tools,
    message_content_to_text,
)


class _FakePrompt:
    def __or__(self, other):
        return other


class _ToolCallingLLM:
    """First call returns tool calls; no-tools path returns final text."""

    def __init__(self):
        self.bind_calls = 0
        self.plain_calls = 0

    def bind_tools(self, tools):
        self.bind_calls += 1

        class _Bound:
            def invoke(self, messages):
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_news",
                            "args": {"query": "NVDA"},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                )

        return _Bound()

    def invoke(self, messages):
        self.plain_calls += 1
        return AIMessage(content="Final news write-up from existing tool results.")


class _PassthroughLLM:
    def bind_tools(self, tools):
        class _Bound:
            def invoke(self, messages):
                return AIMessage(content="Completed without more tools.")

        return _Bound()

    def invoke(self, messages):
        raise AssertionError("plain invoke should not run when tools are not requested")


@pytest.mark.unit
def test_message_content_to_text_handles_blocks():
    assert message_content_to_text("hello") == "hello"
    assert message_content_to_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"


@pytest.mark.unit
def test_force_final_writeup_when_tool_cap_would_discard_call():
    llm = _ToolCallingLLM()
    messages = [
        HumanMessage(content="Analyze NVDA"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_news",
                    "args": {"query": "NVDA"},
                    "id": "prior",
                    "type": "tool_call",
                }
            ],
        ),
        SimpleNamespace(content="tool result", tool_calls=None),
    ]

    out = invoke_analyst_with_tools(
        llm=llm,
        prompt=_FakePrompt(),
        tools=[],
        messages=messages,
        max_tool_rounds=2,
        report_key="news_report",
    )

    assert out["news_report"] == "Final news write-up from existing tool results."
    assert getattr(out["messages"][0], "tool_calls", None) in (None, [])
    assert llm.plain_calls == 1
    assert llm.bind_calls == 1


@pytest.mark.unit
def test_allows_tool_calls_before_cap():
    llm = _ToolCallingLLM()
    out = invoke_analyst_with_tools(
        llm=llm,
        prompt=_FakePrompt(),
        tools=[],
        messages=[HumanMessage(content="start")],
        max_tool_rounds=3,
        report_key="fundamentals_report",
    )

    assert out["fundamentals_report"] == ""
    assert out["messages"][0].tool_calls
    assert llm.plain_calls == 0


@pytest.mark.unit
def test_writes_report_when_model_stops_calling_tools():
    out = invoke_analyst_with_tools(
        llm=_PassthroughLLM(),
        prompt=_FakePrompt(),
        tools=[],
        messages=[HumanMessage(content="start")],
        max_tool_rounds=2,
        report_key="market_report",
    )
    assert out["market_report"] == "Completed without more tools."


class _BlankFinalLLM:
    def bind_tools(self, tools):
        class _Bound:
            def invoke(self, messages):
                return AIMessage(content="")

        return _Bound()

    def invoke(self, messages):
        return AIMessage(content="")


@pytest.mark.unit
def test_synthesizes_report_from_tool_results_when_model_blank():
    messages = [
        HumanMessage(content="Analyze NVDA"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_news",
                    "args": {"ticker": "NVDA"},
                    "id": "prior",
                    "type": "tool_call",
                }
            ],
        ),
        SimpleNamespace(content="## NVDA News\n\nBig GPU demand story.", tool_call_id="prior"),
    ]
    out = invoke_analyst_with_tools(
        llm=_BlankFinalLLM(),
        prompt=_FakePrompt(),
        tools=[],
        messages=messages,
        max_tool_rounds=2,
        report_key="news_report",
    )
    assert "Big GPU demand story" in out["news_report"]
    assert "News Report" in out["news_report"]
