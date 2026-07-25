"""Shared tool-loop invocation helpers for analyst nodes."""

from __future__ import annotations

from typing import Any


def _count_tool_call_rounds(messages) -> int:
    count = 0
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            count += 1
    return count


def message_content_to_text(content: Any) -> str:
    """Normalize LangChain message content to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" or "text" in block:
                    parts.append(str(block.get("text") or ""))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(part.strip() for part in parts if str(part).strip()).strip()
    return str(content).strip()


def invoke_analyst_with_tools(
    *,
    llm: Any,
    prompt: Any,
    tools: list[Any],
    messages: list[Any],
    max_tool_rounds: int | None,
    report_key: str,
) -> dict[str, Any]:
    """Run one analyst LLM step, forcing a final write-up at the tool-round cap.

    When ``max_tool_rounds`` is set and another tool-call response would be
    discarded by conditional routing (``Msg Clear``), re-invoke without tools
    so ``report_key`` is never left empty.
    """
    tool_chain = prompt | llm.bind_tools(tools)
    result = tool_chain.invoke(messages)
    tool_calls = getattr(result, "tool_calls", None) or []

    prior_rounds = _count_tool_call_rounds(messages)
    would_hit_cap = (
        bool(tool_calls)
        and max_tool_rounds is not None
        and (prior_rounds + 1) >= max_tool_rounds
    )

    if would_hit_cap:
        final_result = (prompt | llm).invoke(messages)
        report = message_content_to_text(getattr(final_result, "content", ""))
        return {
            "messages": [final_result],
            report_key: report,
        }

    report = ""
    if not tool_calls:
        report = message_content_to_text(getattr(result, "content", ""))

    return {
        "messages": [result],
        report_key: report,
    }
