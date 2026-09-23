# Vein Reports — Status

Last updated: 2026-08-07

## In progress / recently shipped

- **Performance Optimization Guide** (2026-08-07): Comprehensive docs in `docs/PERFORMANCE_OPTIMIZATION.md` covering tier profiles (`free/pro/team`), configuration-only optimizations, analyst selection, and ready-to-use presets (Ultra-Fast, Balanced, Quality). Updated `.env.example` with tier controls and news limits.
- Vein Aggregator integration (briefs endpoint, section-aware formatting)
- Aggregator client timeout default **240s** + retry (cold Railway fetches)
- Job disk recovery on startup (requeue queued; fail or resume interrupted)
- Railway deployment docs for Trinity services + volume guidance
- MiniMax M2.5 removed from CLI catalog defaults (prefer M2.7 / M3)

## Known production notes

- Mount a Railway volume on `TRADINGAGENTS_SERVICE_REPORTS_DIR` or jobs/artifacts are lost on redeploy
- Set `TRADINGAGENTS_DEEP_THINK_LLM=minimax-m2.7` (M2.5 is retired)
- Research Manager structured-output → free-text fallback is expected with thinking models
- StockTwits may 403 from Railway IPs; Reddit may 429 (partial social sections)
- For performance optimization, see `docs/PERFORMANCE_OPTIMIZATION.md` for tier profiles and presets
