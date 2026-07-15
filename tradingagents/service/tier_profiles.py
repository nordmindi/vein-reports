from __future__ import annotations

from typing import Any

# Application-neutral tier defaults — any client may send report_tier on create.
TIER_PROFILES: dict[str, dict[str, Any]] = {
    "free": {
        "pipeline_mode": "lite",
        "max_tool_rounds_per_analyst": 2,
        "news_article_limit": 8,
        "global_news_article_limit": 5,
        "use_deep_research_manager": False,
        "use_deep_portfolio_manager": False,
    },
    "pro": {
        "pipeline_mode": "full",
        "max_tool_rounds_per_analyst": 3,
        "news_article_limit": 15,
        "global_news_article_limit": 8,
        "use_deep_research_manager": False,
        "use_deep_portfolio_manager": True,
    },
    "team": {
        "pipeline_mode": "full",
        "max_tool_rounds_per_analyst": 3,
        "news_article_limit": 20,
        "global_news_article_limit": 10,
        "use_deep_research_manager": False,
        "use_deep_portfolio_manager": True,
    },
}


def apply_tier_profile(config: dict[str, Any], report_tier: str) -> dict[str, Any]:
    """Apply cost/quality defaults for a report tier (does not override explicit models)."""
    tier = (report_tier or "pro").strip().lower()
    profile = TIER_PROFILES.get(tier, TIER_PROFILES["pro"])
    config["report_tier"] = tier
    for key, value in profile.items():
        config[key] = value
    return config
