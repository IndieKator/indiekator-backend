# IndieKator Backend

A FastAPI service that calculates and exposes an IHSG (Indonesia Stock Exchange Composite Index) Fear & Greed Index. The service combines IHSG price momentum with public search interest from Google Trends, persists weekly snapshots in Supabase, and provides a JSON API for the IndieKator dashboard.

## Features

- Weekly IHSG Fear & Greed Index (FGI) on a 0–100 scale
- Ingestion from Sectors.app and Google Trends
- Supabase-backed snapshot history, zone periods, and ingestion-run records
- Manual ingestion endpoint protected by an admin secret
- Automatic daily ingestion at 07:00 Asia/Jakarta
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

The application includes an in-process scheduler. Run a single scheduler-owning application instance unless duplicate daily ingestions are acceptable. Multiple workers or replicas can each register the same scheduled job.

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

When the application starts, APScheduler registers a daily ingestion job at **07:00 Asia/Jakarta (WIB)**. The job uses the same ingestion pipeline as the manual endpoint: there is a single entry point, which upserts `fgi_snapshots`, rebuilds `zone_periods` from those snapshots, and records the attempt in `ingestion_runs`.

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
| `GET` | `/api/fgi` | Returns the latest FGI snapshot and roughly six months of weekly history. Refreshes automatically when the newest snapshot is older than 24 hours. |
| `GET` | `/api/zones` | Returns historical Fear & Greed zone periods. |
| `POST` | `/api/admin/ingest` | Runs a manual ingestion. Requires the `X-Admin-Secret` header. |

`GET /api/fgi` returns `503` when no snapshot exists at all, and sets `is_stale` to `true` when it is serving an outdated snapshot because a refresh attempt failed. `GET /api/zones` returns `404` until a successful ingestion has produced data.

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
