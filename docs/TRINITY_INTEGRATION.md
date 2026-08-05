# Vein Platform Integration (Vein Reports)

Vein Reports orchestrates sibling Vein services via HTTP only. No shared packages or databases.

| Service | Role | Contract |
|---------|------|----------|
| **Vein Explorer** | Supply-chain graph | `vein-context-v1` |
| **Vein Signals** | Technical validation | `reportValidationInput` |
| **Vein Aggregator** | News / sentiment / macro feeds | `vein-intelligence-v1` |
| **Vein Reports** | Multi-agent synthesis + publication | Job API + artifacts |

See also: [Vein Signals — Platform architecture](https://github.com/nordmindi/vein-signals/blob/main/docs/PLATFORM_ARCHITECTURE.md)

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
TRADINGAGENTS_VEIN_EXPLORER_BASE_URL=http://localhost:3001
TRADINGAGENTS_VEIN_SERVICE_API_KEY=<vein-service-key>
```

## Phase 1b — Vein Aggregator intelligence feeds

Optional pull of normalized news, social, macro, and prediction-market data before the agent graph runs:

```env
TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED=1
TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL=http://localhost:3003
# Railway: https://vein-aggregator-production.up.railway.app
TRADINGAGENTS_VEIN_AGGREGATOR_API_KEY=<vein-aggregator-api-key>
# Optional: cold fetches can take ~200s
TRADINGAGENTS_VEIN_AGGREGATOR_TIMEOUT_SEC=240
TRADINGAGENTS_VEIN_AGGREGATOR_MAX_ATTEMPTS=2
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

Accepts Vein Signals `reportValidationInput` plus optional report-side context:

- `supplyChainContext` (Explorer)
- `intelligenceBrief` (Aggregator)
- `reportContext` (cached prior report bias)

Returns `reportValidation` without running the full agent graph.

**Loose coupling:** lite validation does **not** re-check Signals confidence/watchlist gates. If Signals is already non-tradeable → `DEFER_TO_SIGNALS`. If no independent report evidence → `NO_CONTEXT` / `NEUTRAL` (Signals fail-open). Approvals and cautions come only from report-side evidence.

**Reports-side enrichment (Signals unaware):** when caller omits context, lite may optionally fill it from:

| Source | When | Timeout | On failure |
| --- | --- | --- | --- |
| Vein Explorer | `TRADINGAGENTS_VEIN_EXPLORER_ENABLED=1` (or `TRADINGAGENTS_LITE_EXPLORER_ENABLED=1`) | `TRADINGAGENTS_LITE_EXPLORER_TIMEOUT_SEC` (default 8s) | omit / fail-open |
| Vein Aggregator | `TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED=1` (or `TRADINGAGENTS_LITE_AGGREGATOR_ENABLED=1`) | `TRADINGAGENTS_LITE_AGGREGATOR_TIMEOUT_SEC` (default 8s) | omit / fail-open |
| Local report cache | completed jobs / `dashboard.json` for symbol | n/a | omit |

Caller-supplied fields always win. Response includes `liteEnrichment` provenance (`caller` / `explorer` / `aggregator` / `local_cache` / `missing`).

Vein Signals wiring (unchanged — no Explorer/Aggregator env on Signals):

```env
REPORT_SERVICE_ENABLED=1
REPORT_SERVICE_URL=http://localhost:8000/v1/report-validation-lite
REPORT_SERVICE_API_KEY=<same service key>
```

## Safety

- Vein Reports cannot upgrade `WATCHLIST_ONLY` / `BLOCKED` signals to trades
- Vein Reports must not echo Signals technical blockers as its own veto
- Soft confirm / caution preferred over inventing a second technical thesis
- All integrations are optional — disabled env flags = standalone behavior
