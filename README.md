# IndieKator Backend

A FastAPI service that calculates and exposes an IHSG (Indonesia Stock Exchange Composite Index) Fear & Greed Index. The service combines IHSG price momentum with public search interest from Google Trends, persists weekly snapshots in Supabase, and provides a JSON API for the IndieKator dashboard.

## Features

- Weekly IHSG Fear & Greed Index (FGI) on a 0–100 scale
- Ingestion from Sectors.app and Google Trends
- Supabase-backed snapshot history, zone periods, and ingestion-run records
- Manual ingestion endpoint protected by an admin secret
- On-demand ingestion, with an optional daily job at 07:00 Asia/Jakarta
- OpenAPI documentation through FastAPI

## Prerequisites

- Python 3.12 or later
- A Supabase project with the required IndieKator database schema
- A Sectors.app API key
- Access to Google Trends from the runtime environment

> The database schema is managed outside this package. Set up the project database before starting the service. Refer to the repository-level documentation for the schema and migration instructions.

## Quick Start

Run the following commands from the `indiekator-backend` directory.

```bash
cp .env.example .env
# Update .env with your real values.

python -m pip install -e .
uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, create the environment file with:

```powershell
Copy-Item .env.example .env
```

The API is then available at `http://localhost:8000`.

## Configuration

Copy `.env.example` to `.env` and configure the following variables:

| Variable | Required | Description |
| --- | --- | --- |
| `SECTORS_API_KEY` | Yes | API key for Sectors.app IHSG price data. |
| `SUPABASE_URL` | Yes | URL of the Supabase project. |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Server-side Supabase service-role key used to read and write index data. Keep this secret. |
| `ADMIN_SECRET` | Yes in production | Secret required by the manual ingestion endpoint. Replace the example/default value before deployment. |
| `CORS_ORIGINS` | No | Comma-separated browser origins allowed to call the API. Default: `http://localhost:5173`. |
| `IDX_CF_CLEARANCE` | No | Optional IDX Cloudflare clearance cookie for the server's network. Keep it server-side; an expired cookie must be replaced. |
| `ENABLE_SCHEDULER` | No | Set to `true` to enable the in-process 07:00 WIB ingestion job. Default: `false`. |

Example:

```dotenv
SECTORS_API_KEY=your_sectors_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
ADMIN_SECRET=replace-with-a-strong-secret
CORS_ORIGINS=http://localhost:5173,https://app.example.com
```

Never commit `.env` files or expose `SUPABASE_SERVICE_ROLE_KEY` in a browser application.

## Running the Service

### Development

```bash
uvicorn app.main:app --reload --port 8000
```

The `--reload` option is intended for local development only.

### Production

```bash
python -m pip install .
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The application includes an optional in-process scheduler. Set `ENABLE_SCHEDULER=true` to start it. Run a single scheduler-owning application instance unless duplicate daily ingestions are acceptable. Multiple workers or replicas can each register the same scheduled job.

On Cloud Run, leave `ENABLE_SCHEDULER=false`. The FGI endpoints refresh a snapshot on the first request after it becomes more than 24 hours old.

## Cloud Run CI/CD

The [GitHub Actions workflow](.github/workflows/cloud_run.yml) runs tests and builds the Docker image for pull requests to `main`. A push to `main` also pushes an image tagged with the commit SHA to Artifact Registry and deploys it to Cloud Run. It does not run a scheduler or cron job.

Create an Artifact Registry Docker repository and one Google service account for both GitHub deployment and the Cloud Run runtime. Configure a Workload Identity Federation provider restricted to `IndieKator/indiekator-backend` on `refs/heads/main`, then grant its principal `roles/iam.workloadIdentityUser` on that service account. Grant the service account `roles/run.admin` on the project, `roles/artifactregistry.writer` on the repository, and `roles/iam.serviceAccountUser` on itself so it can deploy the Cloud Run service using the same identity. Give it access to the three Secret Manager secrets below. Enable the Cloud Run, Artifact Registry, IAM Credentials, and Secret Manager APIs in the project.

Set these **GitHub repository variables** under Settings → Secrets and variables → Actions → Variables:

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | Google Cloud project ID |
| `GCP_REGION` | Artifact Registry and Cloud Run region, for example `asia-southeast2` |
| `GCP_ARTIFACT_REPOSITORY` | Existing Artifact Registry Docker repository name |
| `GCP_CLOUD_RUN_SERVICE` | Cloud Run service name, for example `indiekator-backend` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full provider name: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL/providers/PROVIDER` |
| `GCP_SERVICE_ACCOUNT` | Service account email used for deployment and Cloud Run runtime |
| `SUPABASE_URL` | Supabase project URL |
| `CORS_ORIGINS` | Frontend origin, for example `https://app.example.com` |

Create Google Secret Manager secrets named `indiekator-sectors-api-key`, `indiekator-supabase-service-role-key`, and `indiekator-admin-secret` with the corresponding `SECTORS_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and a strong `ADMIN_SECRET`. Grant the service account `roles/secretmanager.secretAccessor` on those secrets. Do not put secret values in GitHub variables or in `.env` committed to Git. For Ollama Cloud, create a separate secret and add `OLLAMA_API_KEY=YOUR_SECRET_NAME:latest` to the workflow's `secrets` input; the chat endpoint needs that key.

After merging into `main`, check the workflow run, then request `GET /api/health` and `GET /api/fgi` at the deployed Cloud Run URL. The first FGI request can take longer while it ingests data. Apply the Supabase migrations before using the deployed API. The workflow does not create the Google Cloud project, repository, IAM bindings, secrets, or Supabase schema.

## Initial Data Ingestion

The service does not seed data at startup. After configuring the service, run a first ingestion manually:

```bash
curl -X POST http://localhost:8000/api/admin/ingest \
  -H "X-Admin-Secret: YOUR_ADMIN_SECRET"
```

PowerShell equivalent:

```powershell
Invoke-RestMethod `
  -Method POST `
  -Uri "http://localhost:8000/api/admin/ingest" `
  -Headers @{ "X-Admin-Secret" = "YOUR_ADMIN_SECRET" }
```

A successful response includes the ingestion status, number of weekly snapshots upserted, and a confirmation message.

## Scheduled Ingestion

When `ENABLE_SCHEDULER=true`, APScheduler registers a daily ingestion job at **07:00 Asia/Jakarta (WIB)**. The default is `false`, so no job is scheduled unless explicitly enabled. The job uses the same ingestion pipeline as the manual endpoint: there is a single entry point, which upserts `fgi_snapshots`, rebuilds `zone_periods` from those snapshots, and records the attempt in `ingestion_runs`.

The daily cadence against a weekly index is intentional. Each run recomputes the current in-progress week and refreshes recent Trends values, which providers may revise after the fact.

For production monitoring, check the `ingestion_runs` data in Supabase. The scheduler is process-local and does not provide distributed locking, persistent job storage, or automatic retries.

## API Reference

Interactive API documentation is available while the service is running:

- Swagger UI: [`/docs`](http://localhost:8000/docs)
- ReDoc: [`/redoc`](http://localhost:8000/redoc)
- OpenAPI schema: [`/openapi.json`](http://localhost:8000/openapi.json)

All application routes are prefixed with `/api`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Returns service status and the latest successful ingestion timestamp. |
| `GET` | `/api/fgi` | Returns the latest FGI snapshot together with the full weekly history. |
| `GET` | `/api/fgi/current` | Returns the latest index value, zone, summary, market values, component scores, and week-over-week deltas. |
| `GET` | `/api/fgi/history?range=1y` | Returns chronological weekly points, oldest first. Accepted ranges: `3m`, `6m`, `1y`, `all`. |
| `GET` | `/api/fgi/breakdown` | Returns the latest index value and its weighted price-momentum and public-sentiment components. |
| `GET` | `/api/zones` | Returns historical Fear & Greed zone periods. |
| `GET` | `/api/trading-summary?limit=30&before=YYYY-MM-DD` | Current daily market totals and paginated history. |
| `GET` | `/api/trading-summary/current` | Current daily market totals and previous trading-day changes. |
| `POST` | `/api/admin/ingest` | Runs a manual ingestion. Requires the `X-Admin-Secret` header. |

`GET /api/fgi` returns every snapshot rather than a fixed trailing window, so a client can render any range without a second request. Use `/api/fgi/history` when you want the server to narrow the window instead.

Every `/api/fgi*` endpoint refreshes automatically when the newest snapshot is older than 24 hours. Each returns `503` when no snapshot exists at all; `/api/fgi` and `/api/fgi/current` set `is_stale` to `true` when serving an outdated snapshot because a refresh attempt failed. `GET /api/zones` returns `404` until a successful ingestion has produced data.

`GET /api/fgi/breakdown` reports each component's raw score alongside the weight the engine applies, plus its `contribution` (`value × weight`). Contributions sum to the reported index value, so the breakdown reconstructs the score rather than approximating it.

`GET /api/fgi/current` reports deltas as `vs_last_week` and `vs_month_ago`. The index is weekly, so these are week-over-week comparisons against the previous snapshot and the snapshot four weeks back. A delta is `null` when there is not enough history to compute it.

## Daily Trading Summary

Apply `supabase/migrations/20260927000000_create_trading_summary_sync_state.sql` before deploying the on-demand endpoint. Both trading-summary routes read `GetStockSummary` from IDX when a refresh is due, then upsert the totals to `daily_trading_summary`. During weekday trading hours (09:00–16:15 WIB), successful fetches are reused for 15 minutes. The first request after 16:15 fetches again to replace an intraday value. Once a post-close fetch succeeds, later requests serve Supabase directly until the next trading day. Empty or blocked IDX responses never overwrite stored values.

`current.updated_at` is the last successful fetch time; `current.is_final` means a same-date fetch succeeded after 16:15 WIB. If a due refresh fails while stored data exists, the API returns that data with `current.is_stale=true`. IDX may return a Cloudflare 403 from some server networks, including without an applicable clearance cookie; in that case the API can only serve stored data. The optional `IDX_CF_CLEARANCE` value is never returned to clients.

## Index Methodology

The index is computed weekly. Daily IHSG closes are resampled to week-ending Sunday (`W-SUN`) and joined with weekly Google Trends data over an 18-month lookback. Only weeks with both market and Trends data contribute.

1. **Price momentum** — the weekly IHSG close is compared with its 125-trading-day moving average (MA-125), expressed as a percentage distance.
2. **Public interest** — three Google Trends keywords are fetched independently and averaged, each keeping its own scale.
3. **Score** — the two components are combined with fixed weights.

Formally, where `close` is the weekly close and `trends_mean` is the mean of the three keyword series:

```text
distance_pct = ((close - MA-125) / MA-125) × 100

price_score  = clip(50 + (distance_pct / 6.0) × 50, 0, 100)
search_score = clip(50 + (trends_mean - 50) × sign(distance_pct), 0, 100)

fgi = 0.60 × price_score + 0.40 × search_score
```

Search interest therefore amplifies the prevailing price direction rather than acting independently: when price is above its moving average, high search interest pushes the score toward greed; when price is below, the same high interest pushes it toward fear.

The result is constrained to 0–100 and classified into zones:

| FGI range | Zone |
| --- | --- |
| `fgi ≤ 25` | Extreme Fear |
| `25 < fgi ≤ 45` | Fear |
| `45 < fgi ≤ 55` | Neutral |
| `55 < fgi ≤ 75` | Greed |
| `fgi > 75` | Extreme Greed |

The bounds are inclusive upper limits, so a fractional score such as `25.5` classifies as Fear.

The first 124 trading observations cannot produce an MA-125 and are excluded from calculated output.

Zone periods are derived from the stored snapshot labels by collapsing consecutive weeks that share a zone into a single episode. Because the source is weekly, episode boundaries fall on week-ending dates and `duration_days` lands on multiples of seven.

## Data Sources

- **IHSG prices:** [Sectors.app](https://sectors.app/)
- **Public-interest signal:** Google Trends, locale `id-ID`, geo `ID`, keywords `ihsg`, `idx composite`, and `indeks harga saham gabungan`
- **Persistence:** Supabase PostgreSQL — `fgi_snapshots` for index values, `zone_periods` for the zone log, `ingestion_runs` for run records

External providers may apply availability, rate-limit, or data-revision constraints. A later ingestion can recalculate historical Trends values and associated scores within its lookback window.

## Operational Notes

- `GET /api/health` reports the last successful ingestion, but it is not a full dependency or readiness probe.
- The manual ingestion request executes synchronously and can take time because it fetches external market and Trends data.
- The read endpoints are public. Restrict network access or add an authentication layer if your deployment requires protected data access.
- Keep the service-role key and admin secret in the deployment platform's secret store, not in source control.

## Project Structure

```text
app/
├── api/routes/        # Health, ingestion, FGI, and zone endpoints
├── db/                # Supabase client
├── schemas/           # Request and response models
├── services/          # Data clients, scoring, ingestion, and zone logic
├── config.py          # Environment-based settings
└── main.py            # FastAPI application and scheduler lifecycle
```

## Related Documentation

See the [repository README](../README.md) for the complete project setup, including the frontend and database migration workflow.
