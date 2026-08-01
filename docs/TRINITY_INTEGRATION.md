# Vein Platform Integration (Vein Reports)

Vein Reports orchestrates sibling Vein services via HTTP only. No shared packages or databases.

| Service | Role | Contract |
|---------|------|----------|
| **Vein Explorer** | Supply-chain graph | `vein-context-v1` |
| **Vein Signals** | Technical validation | `reportValidationInput` |
| **Vein Aggregator** | News / sentiment / macro feeds | `vein-intelligence-v1` |
| **Vein Reports** | Multi-agent synthesis + publication | Job API + artifacts |

See also: [Vein Signals — Trinity architecture](https://github.com/nordmindi/vein-signals/blob/main/docs/TRINITY_ARCHITECTURE.md)

## Phase 1 — Embed signal validation in reports

Enable:

```env
TRADINGAGENTS_GOLDEN_TREND_ENABLED=1
TRADINGAGENTS_GOLDEN_TREND_BASE_URL=http://localhost:3001
TRADINGAGENTS_GOLDEN_TREND_API_KEY=<vein-signals-api-key>
TRADINGAGENTS_GOLDEN_TREND_STRATEGY_ID=golden-trend-balanced
```

Report jobs will:

1. `POST {base}/api/v1/signals/analyze` for the ticker
2. Write `signal_validation.json` and `signal_validation.md`
3. Prepend **Vein Signals Validation** to `complete_report.md`
4. Add blocker `SIGNAL_SERVICE_BLOCKS_TRADE` when Vein Signals blocks execution

Optional Vein Explorer pull (when `context_bundle` not supplied on `POST /v1/reports`):

```env
TRADINGAGENTS_VEIN_EXPLORER_ENABLED=1
TRADINGAGENTS_VEIN_EXPLORER_BASE_URL=http://localhost:3002
TRADINGAGENTS_VEIN_SERVICE_API_KEY=<vein-service-key>
```

## Phase 1b — Vein Aggregator intelligence feeds

Optional pull of normalized news, social, macro, and prediction-market data before the agent graph runs:

```env
TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED=1
TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL=http://localhost:3003
TRADINGAGENTS_VEIN_AGGREGATOR_API_KEY=<vein-aggregator-api-key>
```

Report jobs will:

1. `POST {base}/v1/feeds/intelligence/briefs` with `symbol` **or** `target` (sector, commodity, index, crypto), date window, and optional `peer_symbols` from `vein_context_bundle`
2. Store `vein_intelligence_bundle` and `vein_intelligence_briefs` in graph state
3. Sentiment and News analysts consume pre-fetched blocks when the bundle is present
4. `news_retrieval` metadata prefers the bundle's `retrieval.news_retrieval` field

Thematic reports (no equity ticker) use `POST /v1/reports` with `target` instead of `ticker`:

```json
{
  "target": { "type": "sector", "value": "mining" },
  "analysis_date": "2026-07-31",
  "selected_analysts": ["market", "social", "news"]
}
```

Vein Explorer and Golden Trend validation are skipped for non-equity-like targets (sector, commodity).

When disabled, vein-reports falls back to embedded dataflows (legacy standalone behavior).

Contract reference: `tests/fixtures/intelligence_bundle_v1.json` and the vein-aggregator repo `docs/vein-intelligence-v1.md`.

## Phase 2 — Report validation lite (for Vein Signals)

Endpoint:

```http
POST /v1/report-validation-lite
X-API-Key: <TRADINGAGENTS_SERVICE_API_KEY>
```

Accepts Vein Signals `reportValidationInput` (+ optional `supplyChainContext`). Returns `reportValidation` without running the full agent graph.

Vein Signals wiring:

```env
REPORT_SERVICE_ENABLED=1
REPORT_SERVICE_URL=http://localhost:8000/v1/report-validation-lite
REPORT_SERVICE_API_KEY=<same service key>
```

## Safety

- Vein Reports cannot upgrade `WATCHLIST_ONLY` / `BLOCKED` signals to trades
- All integrations are optional — disabled env flags = standalone behavior
