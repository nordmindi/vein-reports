# Vein Reports Service Deployment on Railway

Deploy Vein Reports alongside Vein Aggregator, Vein Signals, and Vein Explorer.

## Prerequisites

1. A Railway account
2. GitHub access to `nordmindi/vein-reports`
3. LLM provider API keys (OpenAI, Ollama Cloud, Google, etc.)
4. Sibling service URLs/keys when Trinity integrations are enabled

## Deploy

1. Open https://railway.app/ → **New Project** → **Deploy from GitHub**
2. Select `nordmindi/vein-reports`
3. Railway uses [`railway.json`](railway.json) / [`Dockerfile.service`](Dockerfile.service)
4. Generate a public domain under **Settings → Networking**

## Required variables

| Variable | Description |
|----------|-------------|
| `TRADINGAGENTS_SERVICE_API_KEY` | Inbound API key (`X-API-Key`) |
| LLM keys for your provider | e.g. `OPENAI_API_KEY`, `OLLAMA_API_KEY`, `GOOGLE_API_KEY` |

## Recommended LLM defaults

Avoid retired MiniMax **M2.5** models (fail with HTTP 410):

```env
TRADINGAGENTS_LLM_PROVIDER=ollama
TRADINGAGENTS_DEEP_THINK_LLM=minimax-m2.7
TRADINGAGENTS_QUICK_THINK_LLM=minimax-m2.7
```

## Trinity integrations (production)

```env
# Vein Aggregator
TRADINGAGENTS_VEIN_AGGREGATOR_ENABLED=1
TRADINGAGENTS_VEIN_AGGREGATOR_BASE_URL=https://vein-aggregator-production.up.railway.app
TRADINGAGENTS_VEIN_AGGREGATOR_API_KEY=<same-as-VEIN_AGGREGATOR_API_KEY>
TRADINGAGENTS_VEIN_AGGREGATOR_TIMEOUT_SEC=240
TRADINGAGENTS_VEIN_AGGREGATOR_MAX_ATTEMPTS=2

# Vein Signals
TRADINGAGENTS_GOLDEN_TREND_ENABLED=1
TRADINGAGENTS_GOLDEN_TREND_BASE_URL=https://veinsignals-production.up.railway.app
TRADINGAGENTS_GOLDEN_TREND_API_KEY=<vein-signals-key>

# Vein Explorer
TRADINGAGENTS_VEIN_EXPLORER_ENABLED=1
TRADINGAGENTS_VEIN_EXPLORER_BASE_URL=https://vein-api-production.up.railway.app
TRADINGAGENTS_VEIN_SERVICE_API_KEY=<vein-service-key>
```

## Job durability (important)

Jobs are persisted under `TRADINGAGENTS_SERVICE_REPORTS_DIR`
(container default: `/home/app/reports/api`).

On Railway:

1. Attach a **volume** mounted at `/home/app/reports` (preferred) **or** `/app/reports`
2. Set:

```env
# Preferred (matches image default and app user home)
TRADINGAGENTS_SERVICE_REPORTS_DIR=/home/app/reports/api

# Also supported — entrypoint chowns /app/reports when starting as root
# TRADINGAGENTS_SERVICE_REPORTS_DIR=/app/reports/api
```

`scripts/docker-entrypoint-service.sh` runs as root on boot, creates `_jobs` / `_logs`,
`chown`s the mount for user `app`, then drops privileges. If the configured path is
still not writable, it falls back to `/home/app/reports/api`.

**Common failure:** volume at `/app/reports` without the new entrypoint →
`PermissionError: ... '/app/reports/api'` and Explorer shows HTTP 503.

On restart:

- **completed / failed** jobs remain pollable
- **queued** jobs are re-submitted
- **running** jobs are marked failed (interrupted) unless:

```env
TRADINGAGENTS_JOB_RESUME_INTERRUPTED=1
```

Without a volume, redeploys wipe in-progress and completed artifacts.

## Other useful variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HOST` / `PORT` | `0.0.0.0` / Railway `PORT` | Bind address |
| `TRADINGAGENTS_SERVICE_WORKERS` | `1` | Concurrent report jobs |
| `TRADINGAGENTS_MAX_DEBATE_ROUNDS` | config default | Debate depth |
| `TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS` | config default | Risk debate depth |

## Verify

```bash
curl https://<your-service>.up.railway.app/health

curl -X POST "https://<your-service>.up.railway.app/v1/reports" \
  -H "X-API-Key: $TRADINGAGENTS_SERVICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"NVDA","analysis_date":"2026-07-31","selected_analysts":["news","social"]}'
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `minimax-m2.5 was retired` | Set deep/quick think LLMs to `minimax-m2.7` or newer |
| Job 404 after deploy | Mount a volume for `TRADINGAGENTS_SERVICE_REPORTS_DIR` |
| 503 / `Permission denied: '/app/reports/api'` | Remount volume at `/home/app/reports` (preferred) or redeploy so entrypoint can `chown`; set `TRADINGAGENTS_SERVICE_REPORTS_DIR=/home/app/reports/api` |
| Aggregator unused / empty news | Raise `TRADINGAGENTS_VEIN_AGGREGATOR_TIMEOUT_SEC` (cold fetches ~200s) |
| Research Manager structured-output warning | Expected with thinking models; free-text fallback continues |
| 401 on `/v1/reports` | Match `X-API-Key` to `TRADINGAGENTS_SERVICE_API_KEY` |

## Security

1. Use a strong `TRADINGAGENTS_SERVICE_API_KEY`
2. Keep sibling service keys in Railway Variables only
3. Railway provides HTTPS on generated domains
