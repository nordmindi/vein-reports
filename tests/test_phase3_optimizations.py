import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict

from tradingagents.agents.utils.debate_context import (
    collect_analyst_reports_for_brief,
    format_debate_analyst_context,
)
from tradingagents.llm_clients.llm_cache import DiskLLMCache, patch_llm_cache


class _StubLLM:
    model_name = "stub-model"

    def __init__(self):
        self.calls = 0

    def invoke(self, input_value, config=None, **kwargs):
        self.calls += 1
        return AIMessage(content=f"echo:{input_value}")

    def bind_tools(self, tools, **kwargs):
        bound = _StubBoundLLM(self, tools)
        return bound


class _StubBoundLLM(_StubLLM):
    def __init__(self, parent: _StubLLM, tools):
        super().__init__()
        self._parent = parent

    def invoke(self, input_value, config=None, **kwargs):
        self._parent.calls += 1
        return AIMessage(content=f"bound:{input_value}")


@pytest.mark.unit
class TestDebateContext:
    def test_uses_debate_brief_when_present(self):
        state = {
            "debate_brief": "Compressed summary",
            "market_report": "Long market report",
        }
        context = format_debate_analyst_context(state)
        assert "Compressed summary" in context
        assert "Long market report" not in context

    def test_falls_back_to_full_reports_including_supply_chain(self):
        state = {
            "market_report": "Market data",
            "supply_chain_report": "Chain risks",
        }
        context = format_debate_analyst_context(state)
        assert "Market data" in context
        assert "Chain risks" in context

    def test_collects_reports_for_brief(self):
        state = {"news_report": "Headlines", "fundamentals_report": "Ratios"}
        combined = collect_analyst_reports_for_brief(state)
        assert "## News" in combined
        assert "## Fundamentals" in combined


@pytest.mark.unit
class TestLLMCache:
    def test_cache_hit_skips_second_invoke(self, tmp_path):
        cache = DiskLLMCache(tmp_path, "TSLA:2026-07-15")
        llm = patch_llm_cache(_StubLLM(), cache)

        first = llm.invoke("same prompt")
        second = llm.invoke("same prompt")

        assert first.content == second.content
        assert cache.stats()["hits"] == 1
        assert cache.stats()["misses"] == 1

    def test_bind_tools_returns_runnable_compatible_object(self, tmp_path):
        cache = DiskLLMCache(tmp_path, "TSLA:2026-07-15")
        llm = patch_llm_cache(_StubLLM(), cache)
        bound = llm.bind_tools([])
        assert hasattr(bound, "invoke")
        assert bound.__class__.__name__ != "CachedLLMProxy"

    def test_different_namespace_misses(self, tmp_path):
        llm_a = _StubLLM()
        llm_b = _StubLLM()
        cache_a = DiskLLMCache(tmp_path / "a", "A:2026-07-15")
        cache_b = DiskLLMCache(tmp_path / "b", "B:2026-07-15")
        patch_llm_cache(llm_a, cache_a).invoke("prompt")
        patch_llm_cache(llm_b, cache_b).invoke("prompt")
        assert llm_a.calls == 1
        assert llm_b.calls == 1

    def test_patch_works_on_pydantic_model(self, tmp_path):
        class PydanticStubLLM(BaseModel):
            model_config = ConfigDict(extra="forbid")
            model_name: str = "pydantic-stub"
            calls: int = 0

            def invoke(self, input_value, config=None, **kwargs):
                self.calls += 1
                return AIMessage(content=str(input_value))

        cache = DiskLLMCache(tmp_path, "TSLA:2026-07-15")
        llm = patch_llm_cache(PydanticStubLLM(), cache)
        llm.invoke("hello")
        llm.invoke("hello")
        assert llm.calls == 1
        assert cache.stats()["hits"] == 1
