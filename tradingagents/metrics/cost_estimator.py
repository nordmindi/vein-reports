from __future__ import annotations

import json
import os
from typing import Any

# USD per 1M tokens — conservative defaults for common hosted models.
# Override via TRADINGAGENTS_MODEL_PRICING_JSON for deployment-specific rates.
DEFAULT_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input_per_million": 0.15, "output_per_million": 0.60},
    "gpt-4o": {"input_per_million": 2.50, "output_per_million": 10.00},
    "gpt-4.1-mini": {"input_per_million": 0.40, "output_per_million": 1.60},
    "gpt-4.1": {"input_per_million": 2.00, "output_per_million": 8.00},
    "gpt-5.4-mini": {"input_per_million": 0.40, "output_per_million": 1.60},
    "gpt-5.4": {"input_per_million": 2.00, "output_per_million": 8.00},
    "gpt-5.5": {"input_per_million": 2.50, "output_per_million": 10.00},
    "claude-sonnet-4-20250514": {"input_per_million": 3.00, "output_per_million": 15.00},
    "claude-3-5-sonnet-20241022": {"input_per_million": 3.00, "output_per_million": 15.00},
    "gemini-2.5-flash": {"input_per_million": 0.15, "output_per_million": 0.60},
    "gemini-2.5-pro": {"input_per_million": 1.25, "output_per_million": 10.00},
}


def load_model_pricing() -> tuple[dict[str, dict[str, float]], str]:
    """Return pricing table and source label (default | env)."""
    raw = os.getenv("TRADINGAGENTS_MODEL_PRICING_JSON")
    if not raw:
        return DEFAULT_MODEL_PRICING.copy(), "default"

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("TRADINGAGENTS_MODEL_PRICING_JSON must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("TRADINGAGENTS_MODEL_PRICING_JSON must be a JSON object")

    normalized: dict[str, dict[str, float]] = {}
    for model, rates in parsed.items():
        if not isinstance(rates, dict):
            continue
        normalized[str(model)] = {
            "input_per_million": float(rates["input_per_million"]),
            "output_per_million": float(rates["output_per_million"]),
        }
    return normalized, "env"


def _resolve_model_rates(
    model_name: str,
    pricing: dict[str, dict[str, float]],
) -> dict[str, float] | None:
    if model_name in pricing:
        return pricing[model_name]

    lowered = model_name.lower()
    for key, rates in pricing.items():
        if key.lower() == lowered:
            return rates

    # Prefix match for versioned model ids (e.g. gpt-4o-mini-2024-07-18).
    for key, rates in pricing.items():
        if lowered.startswith(key.lower()):
            return rates

    return None


def estimate_model_cost_usd(
    model_name: str,
    tokens_in: int,
    tokens_out: int,
    pricing: dict[str, dict[str, float]] | None = None,
) -> float | None:
    table, _ = load_model_pricing() if pricing is None else (pricing, "provided")
    rates = _resolve_model_rates(model_name, table)
    if rates is None:
        return None

    input_cost = (tokens_in / 1_000_000) * rates["input_per_million"]
    output_cost = (tokens_out / 1_000_000) * rates["output_per_million"]
    return round(input_cost + output_cost, 6)


def estimate_usage_cost_usd(
    by_model: dict[str, dict[str, int]],
    pricing: dict[str, dict[str, float]] | None = None,
) -> tuple[float | None, dict[str, float | None], str]:
    """Estimate total USD cost from per-model token usage."""
    table, source = load_model_pricing() if pricing is None else (pricing, "provided")
    breakdown: dict[str, float | None] = {}
    total = 0.0
    priced_any = False
    unknown_models: list[str] = []

    for model_name, usage in by_model.items():
        tokens_in = int(usage.get("tokens_in") or 0)
        tokens_out = int(usage.get("tokens_out") or 0)
        model_cost = estimate_model_cost_usd(model_name, tokens_in, tokens_out, table)
        breakdown[model_name] = model_cost
        if model_cost is None:
            if tokens_in or tokens_out:
                unknown_models.append(model_name)
            continue
        total += model_cost
        priced_any = True

    if not priced_any:
        return None, breakdown, source

    if unknown_models:
        # Partial estimate when some models lack pricing entries.
        return round(total, 4), breakdown, f"{source}:partial"

    return round(total, 4), breakdown, source
