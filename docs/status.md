# Vein Reports — Status

Last updated: 2026-08-02

## In progress / recently shipped

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
