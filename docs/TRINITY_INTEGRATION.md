# Vein Trinity Integration (TradingAgents)

TradingAgents orchestrates **Vein Explorer** (supply chain) and **Vein Signals / Golden Trend** (technical validation) via HTTP only. No shared packages or databases.

See also: `C:\ws\golden-trend\docs\TRINITY_ARCHITECTURE.md`

## Phase 1 — Embed signal validation in reports

Enable:

```env
TRADINGAGENTS_GOLDEN_TREND_ENABLED=1
TRADINGAGENTS_GOLDEN_TREND_BASE_URL=http://localhost:3001
TRADINGAGENTS_GOLDEN_TREND_API_KEY=<signals-api-key>
TRADINGAGENTS_GOLDEN_TREND_STRATEGY_ID=golden-trend-balanced
```

Report jobs will:

1. `POST {base}/api/v1/signals/analyze` for the ticker
2. Write `signal_validation.json` and `signal_validation.md`
3. Prepend **Signal Service Validation** to `complete_report.md`
4. Add blocker `SIGNAL_SERVICE_BLOCKS_TRADE` when the signal blocks execution

Optional Explorer pull (when `context_bundle` not supplied on `POST /v1/reports`):

```env
TRADINGAGENTS_VEIN_EXPLORER_ENABLED=1
TRADINGAGENTS_VEIN_EXPLORER_BASE_URL=http://localhost:3001
TRADINGAGENTS_VEIN_SERVICE_API_KEY=<vein-service-key>
```

## Phase 2 — Report validation lite (for Golden Trend)

Endpoint:

```http
POST /v1/report-validation-lite
X-API-Key: <TRADINGAGENTS_SERVICE_API_KEY>
```

Accepts Golden Trend `reportValidationInput` (+ optional `supplyChainContext`). Returns `reportValidation` without running the full agent graph.

Golden Trend wiring:

```env
REPORT_SERVICE_ENABLED=1
REPORT_SERVICE_URL=http://localhost:8000/v1/report-validation-lite
REPORT_SERVICE_API_KEY=<same service key>
```

## Safety

- Report cannot upgrade `WATCHLIST_ONLY` / `BLOCKED` signals to trades
- All integrations are optional — disabled env flags = standalone behavior
