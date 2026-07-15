from __future__ import annotations

import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult


def _extract_model_name(serialized: dict[str, Any], kwargs: dict[str, Any]) -> str:
    invocation = kwargs.get("invocation_params") or {}
    for key in ("model", "model_name", "model_id"):
        value = invocation.get(key)
        if value:
            return str(value)

    metadata = kwargs.get("metadata") or {}
    for key in ("ls_model_name", "model"):
        value = metadata.get(key)
        if value:
            return str(value)

    serialized_kwargs = serialized.get("kwargs") or {}
    for key in ("model", "model_name"):
        value = serialized_kwargs.get(key)
        if value:
            return str(value)

    model_path = serialized.get("id")
    if isinstance(model_path, list) and model_path:
        return str(model_path[-1])

    return "unknown"


class ReportMetricsCallbackHandler(BaseCallbackHandler):
    """Tracks LLM calls, tool calls, and token usage for a report job."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.by_model: dict[str, dict[str, int]] = {}

    def _bump_model(
        self,
        model_name: str,
        *,
        llm_calls: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        bucket = self.by_model.setdefault(
            model_name,
            {"llm_calls": 0, "tokens_in": 0, "tokens_out": 0},
        )
        bucket["llm_calls"] += llm_calls
        bucket["tokens_in"] += tokens_in
        bucket["tokens_out"] += tokens_out

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        model_name = _extract_model_name(serialized, kwargs)
        with self._lock:
            self.llm_calls += 1
            self._bump_model(model_name, llm_calls=1)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        model_name = _extract_model_name(serialized, kwargs)
        with self._lock:
            self.llm_calls += 1
            self._bump_model(model_name, llm_calls=1)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        model_name = _extract_model_name({}, kwargs)
        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata
                response_metadata = getattr(message, "response_metadata", None) or {}
                model_name = (
                    response_metadata.get("model_name")
                    or response_metadata.get("model")
                    or model_name
                )

        if not usage_metadata:
            return

        tokens_in = int(
            usage_metadata.get("input_tokens")
            or usage_metadata.get("prompt_tokens")
            or 0
        )
        tokens_out = int(
            usage_metadata.get("output_tokens")
            or usage_metadata.get("completion_tokens")
            or 0
        )
        if tokens_in == 0 and tokens_out == 0:
            return

        with self._lock:
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            self._bump_model(model_name, tokens_in=tokens_in, tokens_out=tokens_out)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self.tool_calls += 1

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "by_model": {
                    model: dict(values)
                    for model, values in self.by_model.items()
                },
            }
