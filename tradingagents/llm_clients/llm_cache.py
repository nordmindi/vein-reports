"""Optional disk cache for LangChain chat model invoke results."""

from __future__ import annotations

import hashlib
import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DiskLLMCache:
    def __init__(self, cache_dir: Path, namespace: str):
        self.cache_dir = cache_dir
        self.namespace = namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _path_for_key(self, key: str) -> Path:
        return self.cache_dir / f"{key}.pickle"

    @staticmethod
    def _serialize_input(input_value: Any) -> str:
        if isinstance(input_value, str):
            return input_value
        if isinstance(input_value, list):
            parts: list[str] = []
            for item in input_value:
                if isinstance(item, dict):
                    parts.append(f"{item.get('role', '')}:{item.get('content', '')}")
                else:
                    content = getattr(item, "content", item)
                    parts.append(str(content))
            return "\n".join(parts)
        content = getattr(input_value, "content", input_value)
        if hasattr(input_value, "to_messages"):
            try:
                return DiskLLMCache._serialize_input(input_value.to_messages())
            except Exception:
                pass
        return str(content)

    def make_key(self, model_name: str, input_value: Any) -> str:
        payload = f"{self.namespace}|{model_name}|{self._serialize_input(input_value)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        path = self._path_for_key(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            value = pickle.loads(path.read_bytes())
            self.hits += 1
            return value
        except Exception as exc:
            logger.debug("llm_cache_read_failed key=%s error=%s", key[:12], exc)
            self.misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        path = self._path_for_key(key)
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_bytes(pickle.dumps(value))
            tmp.replace(path)
        except Exception as exc:
            logger.debug("llm_cache_write_failed key=%s error=%s", key[:12], exc)

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}


def _model_name(llm: Any) -> str:
    for attr in ("model_name", "model"):
        value = getattr(llm, attr, None)
        if value:
            return str(value)
    bound = getattr(llm, "bound", None)
    if bound is not None:
        return _model_name(bound)
    return "unknown"


def _safe_setattr(obj: Any, name: str, value: Any) -> None:
    """Set attributes on Pydantic-based LangChain chat models."""
    try:
        setattr(obj, name, value)
    except (ValueError, TypeError):
        object.__setattr__(obj, name, value)


def patch_llm_cache(llm: Any, cache: DiskLLMCache | None) -> Any:
    """Patch invoke on LangChain Runnable LLMs without breaking Runnable typing.

    LangGraph chains such as ``prompt | llm.bind_tools(tools)`` require the LLM
    (and bound variants) to remain LangChain Runnables. We patch ``invoke`` in
    place using ``object.__setattr__`` so Pydantic chat models (e.g.
    NormalizedChatOpenAI) accept the override.
    """
    if cache is None or getattr(llm, "_vein_cache_patched", False):
        return llm

    original_invoke = llm.invoke

    def cached_invoke(input_value, config=None, **kwargs):
        key = cache.make_key(_model_name(llm), input_value)
        hit = cache.get(key)
        if hit is not None:
            return hit
        result = original_invoke(input_value, config, **kwargs)
        cache.put(key, result)
        return result

    _safe_setattr(llm, "invoke", cached_invoke)

    if hasattr(llm, "bind_tools"):
        original_bind_tools = llm.bind_tools

        def bind_tools_with_cache(tools, **kwargs):
            bound = original_bind_tools(tools, **kwargs)
            return patch_llm_cache(bound, cache)

        _safe_setattr(llm, "bind_tools", bind_tools_with_cache)

    if hasattr(llm, "with_structured_output"):
        original_structured = llm.with_structured_output

        def structured_with_cache(schema, **kwargs):
            structured = original_structured(schema, **kwargs)
            return patch_llm_cache(structured, cache)

        _safe_setattr(llm, "with_structured_output", structured_with_cache)

    _safe_setattr(llm, "_vein_cache_patched", True)
    return llm


def wrap_llm_cache(llm: Any, cache_dir: Path, namespace: str, enabled: bool) -> Any:
    if not enabled:
        return llm
    cache = DiskLLMCache(cache_dir / "llm_responses", namespace)
    return patch_llm_cache(llm, cache)
