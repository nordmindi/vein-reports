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


class CachedLLMProxy:
    """Transparent wrapper adding disk cache to LangChain chat models."""

    def __init__(self, llm: Any, cache: DiskLLMCache | None):
        self._llm = llm
        self._cache = cache

    @property
    def model_name(self) -> str:
        return getattr(self._llm, "model_name", getattr(self._llm, "model", "unknown"))

    def invoke(self, input_value, config=None, **kwargs):
        if self._cache is None:
            return self._llm.invoke(input_value, config, **kwargs)
        key = self._cache.make_key(self.model_name, input_value)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._llm.invoke(input_value, config, **kwargs)
        self._cache.put(key, result)
        return result

    def bind_tools(self, tools, **kwargs):
        bound = self._llm.bind_tools(tools, **kwargs)
        return CachedLLMProxy(bound, self._cache)

    def with_structured_output(self, schema, **kwargs):
        structured = self._llm.with_structured_output(schema, **kwargs)
        return CachedLLMProxy(structured, self._cache)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


def wrap_llm_cache(llm: Any, cache_dir: Path, namespace: str, enabled: bool) -> Any:
    if not enabled:
        return llm
    cache = DiskLLMCache(cache_dir / "llm_responses", namespace)
    return CachedLLMProxy(llm, cache)
