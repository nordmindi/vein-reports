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


def _tool_result_texts(messages: list[Any]) -> list[str]:
    """Collect non-empty tool responses already present in the conversation."""
    texts: list[str] = []
    for message in messages:
        name = getattr(message, "type", None) or message.__class__.__name__
        is_tool = name in {"tool", "ToolMessage"} or "ToolMessage" in type(message).__name__
        if not is_tool and not hasattr(message, "tool_call_id"):
            continue
        text = message_content_to_text(getattr(message, "content", ""))
        if text:
            texts.append(text)
    return texts


def synthesize_report_from_tool_results(messages: list[Any], *, report_key: str) -> str:
    """Build a minimal report from tool outputs when the LLM returns blank text."""
    chunks = _tool_result_texts(messages)
    if not chunks:
        return ""
    heading = report_key.replace("_", " ").title()
    body = "\n\n".join(chunks[:8])
    return (
        f"## {heading}\n\n"
        "The analyst did not produce a final narrative after tool use. "
        "The following evidence was retrieved and is published for downstream review:\n\n"
        f"{body}"
    )


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
    so ``report_key`` is never left empty. If the model still returns blank
    text after tools have already produced content, synthesize a fallback
    report from those tool results.
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
        if not report:
            report = synthesize_report_from_tool_results(messages, report_key=report_key)
        return {
            "messages": [final_result],
            report_key: report,
        }

    report = ""
    if not tool_calls:
        report = message_content_to_text(getattr(result, "content", ""))
        if not report:
            report = synthesize_report_from_tool_results(messages, report_key=report_key)

    return {
        "messages": [result],
        report_key: report,
    }
