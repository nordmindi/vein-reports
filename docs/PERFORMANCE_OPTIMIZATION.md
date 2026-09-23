# Vein Reports Performance Optimization Guide

This guide covers strategies to optimize report generation speed without compromising analytical quality.

## Table of Contents

- [Overview](#overview)
- [Quick Wins (Configuration Only)](#quick-wins-configuration-only)
- [Tier Profiles](#tier-profiles)
- [Pipeline Mode Comparison](#pipeline-mode-comparison)
- [Environment Variable Reference](#environment-variable-reference)
- [Recommended Presets](#recommended-presets)
- [Advanced Optimizations](#advanced-optimizations)
- [Performance Metrics](#performance-metrics)

---

## Overview

The report generation pipeline consists of several stages:

1. **Analysts** (Market, News, Social, Fundamentals) - Data collection & initial analysis
2. **Debate Brief** (optional) - Compress analyst reports for debate context
3. **Bull/Bear Debate** (optional) - Investment thesis discussion
4. **Research Manager** (optional) - Synthesize debate into investment plan
5. **Trader** (optional) - Execution context
6. **Risk Debate** (optional) - Aggressive/Conservative/Neutral risk analysis
7. **Portfolio Manager** - Final decision synthesis

**Optimization Levers:**
- Skip debate/risk stages (lite pipeline)
- Reduce debate rounds (already at minimum: 1)
- Limit analyst tool calls per round
- Use faster LLM models for non-critical stages
- Reduce data collection breadth
- Enable LLM response caching

---

## Quick Wins (Configuration Only)

These optimizations require **zero code changes** - just environment variables or API request parameters.

### 1. Use "free" Tier Profile

The fastest way to optimize is using the built-in `free` tier:

```bash
# Environment variable
TRADINGAGENTS_REPORT_TIER=free
```

Or via API:

```json
{
  "ticker": "AAPL",
  "report_tier": "free"
}
```

**Impact:** ~40-60% faster
- Pipeline: `lite` (skips debate/risk stages)
- Tool rounds: 2 per analyst (vs 3 in pro/team)
- News articles: 8 per ticker, 5 global (vs 15/8 or 20/10)

**Quality Trade-off:** Lower - skips multi-agent debate/validation, less comprehensive data

---

### 2. Custom Balanced Preset

For better quality than "free" while staying fast, use custom config:

```bash
# .env or environment
TRADINGAGENTS_REPORT_TIER=pro
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1          # Already default
TRADINGAGENTS_MAX_RISK_ROUNDS=1            # Already default
```

Plus API request:

```json
{
  "ticker": "AAPL",
  "report_tier": "custom",
  "pipeline_mode": "full",
  "max_tool_rounds_per_analyst": 2,
  "news_article_limit": 12,
  "global_news_article_limit": 6,
  "use_deep_research_manager": false,
  "use_deep_portfolio_manager": false
}
```

**Impact:** ~20-30% faster than default "pro"
- Keeps debate/risk pipeline (quality retention)
- Reduces tool rounds from 3 → 2
- Uses quick models for all stages
- Moderate data reduction

**Quality Trade-off:** Minimal - retains multi-agent debate with slightly less data depth

---

### 3. Analyst Selection

Run only the analysts needed for your use case:

```json
{
  "ticker": "AAPL",
  "selected_analysts": ["market", "news"]
}
```

**Default:** `["market", "social", "news", "fundamentals"]`

**Impact:** ~10-15% faster per analyst removed
- `market`: Price action, technicals (fast, 1-2 tool calls)
- `news`: News + macro indicators (moderate, 2-3 tool calls)
- `social`: Sentiment analysis (fast, 1 tool call)
- `fundamentals`: Balance sheet, cash flow, income (slow, 3+ tool calls)

**Quality Trade-off:** Variable - depends on which dimension you skip

**Recommendations:**
- **Speed priority:** `["market", "news"]` (technical + catalysts)
- **Quality priority:** All 4 analysts
- **Quick scan:** `["market"]` only

---

## Tier Profiles

Built-in tier profiles in `tradingagents/service/tier_profiles.py`:

| Setting                         | free          | pro           | team          |
|---------------------------------|---------------|---------------|---------------|
| **Pipeline Mode**               | `lite`        | `full`        | `full`        |
| **Tool Rounds/Analyst**         | 2             | 3             | 3             |
| **News Articles (ticker)**      | 8             | 15            | 20            |
| **News Articles (global)**      | 5             | 8             | 10            |
| **Deep Research Manager**       | No            | No            | No            |
| **Deep Portfolio Manager**      | No            | Yes           | Yes           |
| **Compress Debate Context**     | No            | Yes           | Yes           |
| **LLM Cache Enabled**           | Yes           | Yes           | Yes           |
| **Est. Time (full report)**     | 60-90s        | 120-180s      | 150-200s      |

### When to Use Each Tier

- **free**: Quick scans, high-frequency analysis, dev/testing
- **pro**: Production default, balanced quality/speed
- **team**: Maximum depth, low-frequency critical decisions

---

## Pipeline Mode Comparison

### Lite Pipeline (`pipeline_mode: "lite"`)

**Flow:** Analysts → Lite Decision → END

**Skips:**
- Bull/Bear debate
- Research Manager synthesis
- Trader execution context
- Risk debate (Aggressive/Conservative/Neutral)
- Portfolio Manager multi-stage synthesis

**Output:** Single-pass decision from analyst reports

**Use Cases:**
- Screening large watchlists
- Daily quick checks
- Non-critical decisions
- Development/testing

**Estimated Time:** 50-70% of full pipeline

---

### Full Pipeline (`pipeline_mode: "full"`)

**Flow:** Analysts → Debate Brief → Bull ↔ Bear Debate → Research Manager → Trader → Risk Debate (Aggressive ↔ Conservative ↔ Neutral) → Portfolio Manager → END

**Advantages:**
- Multi-perspective validation
- Explicit bull/bear case exploration
- Risk-adjusted synthesis
- Execution context awareness

**Use Cases:**
- Production reports
- Client-facing analysis
- Critical investment decisions

**Estimated Time:** Full duration

---

## Environment Variable Reference

### Performance-Related Variables

```bash
# Tier (highest-level control)
TRADINGAGENTS_REPORT_TIER=pro              # free|pro|team

# Debate/Risk Rounds (already at minimum: 1)
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1          # Bull↔Bear iterations
TRADINGAGENTS_MAX_RISK_ROUNDS=1            # Risk analyst iterations

# LLM Models (use faster models for both)
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.4-mini  # Normally gpt-5.5
TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4-mini

# LLM Cache (reduces redundant calls)
TRADINGAGENTS_LLM_CACHE_ENABLED=true       # Default: enabled in tier profiles

# Data Collection Limits (reduce token usage)
TRADINGAGENTS_NEWS_ARTICLE_LIMIT=10        # Default: 20
TRADINGAGENTS_GLOBAL_NEWS_ARTICLE_LIMIT=5  # Default: 10
```

### Not Recommended for Speed Optimization

These can reduce variation but don't significantly impact speed:

```bash
# Temperature (affects output consistency, not speed)
TRADINGAGENTS_TEMPERATURE=0.0

# Checkpoint (for fault tolerance, minimal speed impact)
TRADINGAGENTS_CHECKPOINT_ENABLED=false
```

---

## Recommended Presets

### Preset 1: Ultra-Fast (free tier)

**Use Case:** Rapid screening, dev/test

```bash
# .env
TRADINGAGENTS_REPORT_TIER=free
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4-mini
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.4-mini
TRADINGAGENTS_LLM_CACHE_ENABLED=true
```

```json
// API request
{
  "ticker": "AAPL",
  "report_tier": "free",
  "selected_analysts": ["market", "news"]
}
```

**Expected Time:** 60-90 seconds (full report)

**Quality:** Basic - single-pass decision, limited data

---

### Preset 2: Balanced (custom pro)

**Use Case:** Production default, quality with speed

```bash
# .env
TRADINGAGENTS_REPORT_TIER=pro
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4-mini
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.4       # Fast but capable
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1
TRADINGAGENTS_LLM_CACHE_ENABLED=true
```

```json
// API request
{
  "ticker": "AAPL",
  "report_tier": "custom",
  "pipeline_mode": "full",
  "max_tool_rounds_per_analyst": 2,
  "news_article_limit": 12,
  "global_news_article_limit": 6,
  "use_deep_research_manager": false,
  "use_deep_portfolio_manager": false
}
```

**Expected Time:** 100-130 seconds (full report)

**Quality:** Good - retains debate/risk validation with moderate data depth

---

### Preset 3: Quality Priority (current default)

**Use Case:** Critical decisions, client reports

```bash
# .env
TRADINGAGENTS_REPORT_TIER=pro
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4-mini
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.5
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1
TRADINGAGENTS_LLM_CACHE_ENABLED=true
```

```json
// API request
{
  "ticker": "AAPL",
  "report_tier": "pro",
  "selected_analysts": ["market", "social", "news", "fundamentals"]
}
```

**Expected Time:** 120-180 seconds (full report)

**Quality:** High - full pipeline, deep reasoning models, comprehensive data

---

## Advanced Optimizations

### 1. Reduce Debate Rounds to 0 (Code Change Required)

**Current minimum:** 1 round each for debate/risk

**Potential optimization:** Allow 0 rounds (immediate manager synthesis)

**Implementation:**

```python
# tradingagents/graph/conditional_logic.py
def should_continue_debate(self, state):
    count = state["investment_debate_state"]["count"]
    # Change from: if count < self.max_debate_rounds:
    if self.max_debate_rounds > 0 and count < self.max_debate_rounds:
        # Continue debate
    else:
        # Skip directly to Research Manager
```

**Impact:** ~15-20% faster (skips debate loop)

**Quality Trade-off:** Moderate - loses bull/bear perspective contrast

**Risk:** May reduce decision robustness for contrarian cases

---

### 2. Parallel Analyst Execution

**Current:** Sequential analyst execution (Market → Social → News → Fundamentals)

**Optimization:** Run analysts in parallel (requires LangGraph changes)

**Implementation complexity:** High (requires graph restructuring)

**Impact:** ~30-40% faster (if I/O bound)

**Quality Trade-off:** None (same outputs, different order)

**Risk:** Requires careful state management, potential race conditions

---

### 3. Streaming Output

**Current:** Full pipeline completes before response

**Optimization:** Stream partial results as pipeline progresses

**Impact:** Perceived speed improvement (user sees progress)

**Implementation:** Use LangGraph streaming API (already supported in debug mode)

---

### 4. Caching Intelligence Bundles

**Current:** Vein Aggregator cache (already implemented)

**Additional:** Cache analyst reports by ticker+date+config

**Impact:** ~80-90% faster for repeated analyses (cache hit)

**Quality Trade-off:** Staleness risk if market moves significantly

**Implementation:** Extend `llm_cache` to cover full analyst outputs

---

## Performance Metrics

Track these metrics to measure optimization impact:

```json
// cost_metrics.json (generated per report)
{
  "duration_sec": 142.5,
  "pipeline_mode": "full",
  "report_tier": "pro",
  "selected_analysts": ["market", "news", "fundamentals"],
  "usage": {
    "llm_calls": 28,
    "tool_calls": 15,
    "tokens_in": 45000,
    "tokens_out": 8500
  },
  "estimated_cost_usd": 0.12
}
```

**Key Metrics:**
- `duration_sec`: Total wall-clock time
- `llm_calls`: Number of LLM invocations (lower = faster)
- `tool_calls`: Data fetch operations (lower = less latency)
- `tokens_in`: Context size (affects LLM speed)
- `estimated_cost_usd`: Per-report cost

---

## Summary: Optimization Decision Tree

```
Need absolute fastest? (60-90s)
├─ Yes → Use Preset 1 (Ultra-Fast free tier)
└─ No → Need debate/risk validation?
    ├─ Yes → Use Preset 2 (Balanced custom pro)
    │        Quality: Good, Speed: ~100-130s
    └─ No → Use Preset 3 (Quality Priority)
             Quality: High, Speed: ~120-180s

Screening 100+ tickers?
└─ Use Preset 1 + selected_analysts: ["market"]
   Est. ~30-45s per ticker

Client-facing reports?
└─ Use Preset 3 (full pipeline, all analysts)
   Est. ~120-180s per ticker
```

---

## Next Steps

1. **Test with your workload:** Try presets with representative tickers
2. **Monitor metrics:** Compare `cost_metrics.json` across configurations
3. **Adjust thresholds:** Fine-tune analyst selection and tool rounds
4. **Consider caching:** Enable for repeated analyses (same ticker/date)
5. **Profile bottlenecks:** Use `duration_sec` and `tool_calls` to identify slow stages

---

## Questions or Issues?

- Check `docs/status.md` for known performance issues
- Review `tradingagents/service/tier_profiles.py` for tier defaults
- See `tradingagents/default_config.py` for all configurable parameters
