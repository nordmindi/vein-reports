# Vein Explorer → Trading Report Service — Integration Guide

**Audience:** Engineers building or operating the TradingAgents (or compatible) report
generation service.

**Purpose:** When a Vein user requests a trading intelligence report from their portfolio
watchlist, Vein Explorer enriches your `POST /v1/reports` call with a **`context_bundle`**
containing supply-chain intelligence from the **Vein Graph**. This document describes exactly
what to expect and how we recommend you use it.

**Vein internal reference:** [trading-report-vein-context.md](./trading-report-vein-context.md)

---

## 1. Overview

Vein Explorer traces products and services into supply-chain trees, then aggregates repeated
traces into a canonical **Vein Graph** (entities, dependencies, chokepoints, related tickers).

Your service already receives:

| Field | Description |
|-------|-------------|
| `ticker` | Uppercase symbol (e.g. `TSLA`) |
| `analysis_date` | ISO date `YYYY-MM-DD` |
| `report_tier` | `free` or `pro` |
| `user_id` | Vein user id (for your job tracking) |
| `output_language` | Optional language code (e.g. `en`, `sv`) |

**New (when Vein Graph has been populated):** Vein also sends:

| Field | Description |
|-------|-------------|
| `context_bundle` | JSON object, schema **`vein-context-v1`** (see §3) |

The bundle is **always sent** when Vein creates a report job (even if empty). Your service
should treat it as **optional for backward compatibility** — older Vein deployments may omit it.

Instrument identity must be exact. `context_bundle.primary_symbol` must match the submitted
`ticker`. If the intended asset is a futures contract such as `KC=F`, send `ticker: "KC=F"`
and `primary_symbol: "KC=F"`. Sending `ticker: "KC"` analyzes a different listed instrument
and the TradingAgents validator will treat the coffee supply-chain context as non-authoritative.

---

## 2. Request flow

```
Vein user (portfolio watchlist)
    → POST /v1/portfolio/reports { symbol }
        → Vein resolves symbol in Vein Graph (exposure analysis)
        → Vein builds context_bundle
        → POST /v1/reports { ticker, …, context_bundle }
            → Your async job (queued → running → completed)
        → Vein polls GET /v1/reports/:job_id
        → Vein stores summary + validation metadata
```

**Authentication:** Vein calls your API with `X-API-Key` (configured in Vein as
`TRADING_REPORTS_API_KEY`). No change required on your side.

**Idempotency:** Each Vein report create is a new job. Vein stores `job_id` and does not
retry create on your behalf unless the user clicks generate again.

---

## 3. `context_bundle` schema (`vein-context-v1`)

### 3.1 Top-level fields

| Field | Type | Always present | Description |
|-------|------|----------------|-------------|
| `version` | string | yes | Always `"vein-context-v1"` |
| `primary_symbol` | string | yes | Same as `ticker` (uppercase) |
| `has_graph_coverage` | boolean | yes | `true` if Vein Graph knows this ticker |
| `company` | object \| null | yes | Resolved company entity; `null` if no coverage |
| `anchor_elements` | array | yes | Product/material nodes linked to the ticker |
| `downstream_products` | array | yes | What depends on those anchors (by hop distance) |
| `related_companies` | array | yes | Other tickers in the same supply-chain neighbourhood |
| `chokepoints` | array | yes | Curated high-risk nodes (see §3.4) |
| `peer_tickers_for_news` | string[] | yes | Symbols for widening news/social queries |
| `watchlist_notes` | string \| null | yes | User-authored notes from Vein watchlist |
| `generated_at` | string (ISO 8601) | yes | When Vein built this bundle |

### 3.2 `company` object (when `has_graph_coverage` is true)

```json
{
  "name": "Tesla, Inc.",
  "symbol": "TSLA",
  "is_chokepoint": false
}
```

### 3.3 `anchor_elements`

Products or materials in the graph that the company is **traded against** (exposure anchor).

```json
[{ "name": "Electric vehicles" }]
```

### 3.4 `downstream_products`

Nodes that **depend on** anchor elements — “picks and shovels” / second-order exposure.

```json
[
  {
    "name": "EV battery packs",
    "category": "energy",
    "hops": 1,
    "is_chokepoint": true
  }
]
```

| Subfield | Meaning |
|----------|---------|
| `hops` | Graph distance from anchor (1 = direct downstream) |
| `is_chokepoint` | Vein flagged this node as a hidden chokepoint |
| `category` | Optional ontology label (may be null) |

### 3.5 `related_companies`

Other **tradeable companies** attached to elements in the same neighbourhood.

```json
[
  {
    "symbol": "ALB",
    "name": "Albemarle Corporation",
    "via": "Lithium refining",
    "via_chokepoint": true
  }
]
```

| Subfield | Meaning |
|----------|---------|
| `via` | Supply-chain element that links this company to the primary ticker |
| `via_chokepoint` | The linking element is a chokepoint |

### 3.6 `chokepoints`

Deduped list (max 20) derived from downstream chokepoints and chokepoint-linked suppliers.
Use for a dedicated **Supply Chain & Chokepoint** section.

```json
[
  { "name": "EV battery packs", "category": "energy", "hops": 1 },
  { "name": "Lithium refining", "category": null, "hops": 0, "via": "ALB" }
]
```

| Subfield | Meaning |
|----------|---------|
| `via` | Present when chokepoint is tied to a related company symbol |

### 3.7 `peer_tickers_for_news`

Up to **24** uppercase symbols (excludes `primary_symbol`). Built from `related_companies`.

**Critical use case:** When your news or social tools return **zero articles** for the
primary ticker, retry with these symbols and/or sector-relevant queries derived from
`anchor_elements` and `downstream_products` names.

### 3.8 `watchlist_notes`

Free-text notes the user saved on their Vein watchlist entry. May contain personal thesis
(e.g. “Watch China exposure”). Use for **framing only** — not as verified facts. May be
`null`.

---

## 4. Full example request

```http
POST /v1/reports HTTP/1.1
Host: your-report-service.example.com
Content-Type: application/json
X-API-Key: <shared-secret>

{
  "ticker": "TSLA",
  "analysis_date": "2026-06-30",
  "report_tier": "pro",
  "user_id": "clx9abc123",
  "output_language": "en",
  "context_bundle": {
    "version": "vein-context-v1",
    "primary_symbol": "TSLA",
    "has_graph_coverage": true,
    "company": {
      "name": "Tesla, Inc.",
      "symbol": "TSLA",
      "is_chokepoint": false
    },
    "anchor_elements": [{ "name": "Electric vehicles" }],
    "downstream_products": [
      {
        "name": "EV battery packs",
        "category": "energy",
        "hops": 1,
        "is_chokepoint": true
      }
    ],
    "related_companies": [
      {
        "symbol": "ALB",
        "name": "Albemarle Corporation",
        "via": "Lithium refining",
        "via_chokepoint": true
      }
    ],
    "chokepoints": [
      { "name": "EV battery packs", "category": "energy", "hops": 1 },
      { "name": "Lithium refining", "category": null, "hops": 0, "via": "ALB" }
    ],
    "peer_tickers_for_news": ["ALB"],
    "watchlist_notes": "Focus on margin and battery supply",
    "generated_at": "2026-06-30T18:00:00.000Z"
  }
}
```

### 4.1 No graph coverage (ticker unknown to Vein)

Vein still sends `context_bundle` with `has_graph_coverage: false` and empty arrays.
**Do not invent supply-chain claims** in this case.

```json
{
  "version": "vein-context-v1",
  "primary_symbol": "OBSCURE",
  "has_graph_coverage": false,
  "company": null,
  "anchor_elements": [],
  "downstream_products": [],
  "related_companies": [],
  "chokepoints": [],
  "peer_tickers_for_news": [],
  "watchlist_notes": null,
  "generated_at": "2026-06-30T18:00:00.000Z"
}
```

---

## 5. Recommended integration behaviour

**TradingAgents status:** implemented. The current service accepts `context_bundle`,
adds a deterministic Supply Chain analyst for pro jobs when the bundle is present,
persists the bundle in graph state as `vein_context_bundle`, writes
`supply_chain_report`, and saves `1_analysts/supply_chain.md` in the report tree.

### 5.1 Add a Supply Chain & Chokepoint analyst

When `has_graph_coverage === true`:

1. Inject `context_bundle` into a new analyst prompt (or tool context).
2. Produce a markdown section **Supply Chain & Chokepoint Analysis** covering:
   - Anchor products (`anchor_elements`)
   - Key dependencies (`downstream_products`, sorted by `hops`)
   - Hidden chokepoints (`chokepoints`) with plain-language risk explanation
   - Related listed peers (`related_companies`) and how they connect via `via`
3. **Cite Vein as the structural source**, e.g. “Per Vein Graph supply-chain analysis (as of
   `generated_at`)…” — distinguish from market/news/fundamental data.
4. State clearly that Vein structural data is **model-assisted and may not be filing-verified**
   unless you add your own verification layer.

When `has_graph_coverage === false`:

- Omit the section or state: “No Vein supply-chain coverage for this symbol yet.”
- Do not block the report solely for missing Vein data.

TradingAgents currently emits a short no-coverage Supply Chain section stating
that no supply-chain claims are made from missing Vein coverage.

### 5.2 News / social widening (fixes “news vacuum”)

Pseudocode:

```
articles = get_news(ticker=primary_symbol, window=analysis_window)
if articles.is_empty() and context_bundle.peer_tickers_for_news.length > 0:
    for peer in context_bundle.peer_tickers_for_news:
        articles += get_news(ticker=peer, window=analysis_window)
    annotate: "Primary ticker had thin news coverage; supplemented with supply-chain peers: …"
if articles.is_empty():
    try queries from anchor_elements + downstream_products names (not invented events)
```

This directly addresses cases where the primary ticker returns zero articles but supply-chain
peers (e.g. lithium, semis) have coverage.

TradingAgents records this as `PEER_NEWS_FALLBACK_USED` and annotates peer articles
with `source_type: "vein_peer_news"`, `peer_ticker`, and
`supplemental_for: "primary_ticker_news_vacuum"`.

### 5.3 Portfolio manager / validator

- Treat supply-chain chokepoints as **structural risk factors** alongside technicals and
  fundamentals — not as buy/sell triggers alone.
- If Vein provides chokepoints but news is empty, **do not** downgrade to
  `INSUFFICIENT_EVIDENCE` solely for lack of news — structural evidence may still support a
  conditional thesis (with appropriate caveats).

### 5.4 User notes

If `watchlist_notes` is non-null, you may reference it in the executive summary framing
(“User research focus: …”). Do not treat it as market fact.

---

## 6. What Vein does **not** send (today)

| Not included | Notes |
|--------------|-------|
| Full trace graph JSON | Only normalized exposure projection |
| Evidence confidence per edge | Planned for `vein-context-v2` |
| Vein Score numeric tier | Planned for v2 |
| Scenario / disruption simulation results | Planned for v2 |
| SEC filing excerpts | Vein has EDGAR pipeline internally; not passed yet |

If you need additional fields, contact the Vein team before assuming they exist.

---

## 7. Versioning

| `version` | Status |
|-----------|--------|
| `vein-context-v1` | **Current** — described in this document |

When Vein ships `vein-context-v2`, the `version` field will change. Your service should:

- Accept unknown versions gracefully (use fields you understand).
- Log `version` on each job for debugging.

---

## 8. Response expectations (unchanged)

Vein continues to poll the existing job API. TradingAgents now returns artifact URLs in
both the create response and completed status response:

| Endpoint | Use |
|----------|-----|
| `GET /v1/reports/:job_id` | Status, raw `decision`, and artifact URLs |
| `GET /v1/reports/:job_id/json` | Full final-state JSON |
| `GET /v1/reports/:job_id/pdf` | PDF proxy download for user |
| `GET /v1/reports/:job_id/dashboard` | Canonical public recommendation/action |
| `GET /v1/reports/:job_id/validation` | Validation status, blocking issues, metadata |
| `GET /v1/reports/:job_id/evidence` | Decision evidence bundle |

Vein should prefer `dashboard.json` over Markdown/PDF scraping for product UI decisions:

- `recommendation`
- `action`
- `decision_status`
- `report_status`
- target fields, when present

If `report_status` or `decision_status` is blocked, the canonical output is:

```json
{
  "recommendation": "INSUFFICIENT_EVIDENCE",
  "action": "NO_CURRENT_TRANSACTION"
}
```

Vein may also parse from full-state JSON (when present):

- `validation_status` / `publication_status`
- `recommendation`
- Evidence gap language in analyst markdown (news vacuum, missing evidence sections)

TradingAgents includes `supply_chain_report` in `final_state`, making downstream
parsing easier without changing the response envelope.

---

## 9. Testing checklist (report service)

- [x] `POST /v1/reports` with no `context_bundle` — legacy behaviour unchanged
- [x] `has_graph_coverage: false` — no fabricated supply-chain claims
- [x] `has_graph_coverage: true` with TSLA-like bundle — Supply Chain section appears
- [x] Primary ticker returns 0 news articles — peers from `peer_tickers_for_news` queried
- [x] `watchlist_notes` reflected in framing, not as verified fact
- [x] `version: vein-context-v1` persisted with the job request/context bundle
- [x] Swagger documents `context_bundle`, `supply_chain`, and artifact endpoints
- [x] Completed jobs expose dashboard, validation, and evidence JSON endpoints
- [x] Instrument mismatch, such as `KC` vs `KC=F`, is blocked from becoming actionable

Current automated coverage:

- `tests/test_service_runner.py`
- `tests/test_structured_agents.py`
- `tests/test_report_validation.py`
- `tests/test_service_api.py`

---

## 10. Contact & repository

- **Vein Explorer:** Supply chain & trade explorer (Next.js + NestJS monorepo)
- **Vein API prefix:** `/v1` (user-facing report create: `POST /v1/portfolio/reports`)
- **This integration:** Vein → your `POST /v1/reports` with `context_bundle`

For schema questions or v2 field requests, coordinate with the Vein engineering team.

---

## Appendix A — Copy-paste handoff (email / Slack)

**Subject:** Vein Explorer now sends `context_bundle` on report create — integration guide

Hi team,

Vein Explorer now attaches a **`context_bundle`** (`vein-context-v1`) to every `POST /v1/reports` job we enqueue from portfolio watchlists. It contains supply-chain intelligence from our Vein Graph: anchor products, downstream dependencies, chokepoints, related tickers, and **`peer_tickers_for_news`** for widening news/social when the primary symbol has thin coverage.

**Full spec (schema, examples, recommended behaviour):**  
`docs/trading-report-service-vein-integration.md` in the Vein repo  
(or share the file directly from `https://github.com/nordmindi/supply-chain-explorer/blob/main/docs/trading-report-service-vein-integration.md`)

**What we need on your side:**

1. Read `context_bundle` on create (backward compatible if omitted).
2. Add a **Supply Chain & Chokepoint** analyst section when `has_graph_coverage === true`.
3. When primary-ticker news returns zero articles, also query `peer_tickers_for_news`.
4. Do **not** invent supply-chain claims when `has_graph_coverage === false`.

**Example fields:** `chokepoints`, `downstream_products`, `related_companies`, `watchlist_notes` (user framing only).

Happy to walk through a live payload or test with TSLA once you’ve pulled the doc. Vein is live on our side as of commit `38c176e`+.

Thanks,  
[Your name]

---

### Slack (short)

> Vein now sends `context_bundle` on `POST /v1/reports` — supply-chain chokepoints, downstream products, and `peer_tickers_for_news` for when the main ticker has a news vacuum. Integration guide: `docs/trading-report-service-vein-integration.md`. Main ask: Supply Chain analyst section + widen news queries to peer tickers. `has_graph_coverage: false` → don’t fabricate chain data.
