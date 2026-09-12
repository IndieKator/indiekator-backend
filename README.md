# IndieKator Backend

A FastAPI service that calculates and exposes an IHSG (Indonesia Stock Exchange Composite Index) Fear & Greed Index. The service combines IHSG price momentum with public interest in the `ihsg` search term from Google Trends, persists the calculated records in Supabase, and provides a JSON API for the IndieKator dashboard.

## Features

- IHSG Fear & Greed score on a 0–100 scale
- Daily ingestion from Sectors.app and Google Trends
- Supabase-backed sentiment history, zone periods, and ingestion-run records
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

A successful response includes the ingestion status, number of daily records upserted, and a confirmation message.

## Scheduled Ingestion

When the application starts, APScheduler registers a daily ingestion job at **07:00 Asia/Jakarta (WIB)**. The job uses the same ingestion pipeline as the manual endpoint.

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
| `GET` | `/api/sentiment/current` | Returns the latest Fear & Greed score, zone, summary, market values, and score deltas. |
| `GET` | `/api/sentiment/history?range=1y` | Returns chronological sentiment points. Accepted ranges: `3m`, `6m`, `1y`, `all`. |
| `GET` | `/api/sentiment/breakdown` | Returns the latest score and its price-momentum and public-sentiment components. |
| `GET` | `/api/zones` | Returns historical Fear & Greed zone periods. |
| `POST` | `/api/admin/ingest` | Runs a manual ingestion. Requires the `X-Admin-Secret` header. |

The public sentiment and zone endpoints return `404` until a successful ingestion has produced data.

## Index Methodology

The index is calculated for dates with both market and Trends data available:

1. **Price momentum** — IHSG closing price is compared with its 125-trading-day moving average (MA-125).
2. **Public interest** — Google Trends values for `ihsg` are normalized to a 0–100 scale over the ingestion window.
3. **Score** — A close above MA-125 places the score in the 50–100 range; a close at or below MA-125 places it in the 0–50 range. Higher normalized search interest increases the distance from 50.

Formally, for normalized Google Trends value `T` in `[0, 100]`:

```text
score = 50 + 0.5 × T  when close > MA-125
score = 50 - 0.5 × T  when close ≤ MA-125
```

The result is constrained to 0–100 and mapped to Fear & Greed zones. The first 124 trading observations cannot produce an MA-125 and are excluded from calculated output.

## Data Sources

- **IHSG prices:** [Sectors.app](https://sectors.app/)
- **Public-interest signal:** Google Trends, keyword `ihsg`, locale `id-ID`
- **Persistence:** Supabase PostgreSQL

External providers may apply availability, rate-limit, or data-revision constraints. A later ingestion can recalculate historical normalized Trends values and associated scores within its lookback window.

## Operational Notes

- `GET /api/health` reports the last successful ingestion, but it is not a full dependency or readiness probe.
- The manual ingestion request executes synchronously and can take time because it fetches external market and Trends data.
- The read endpoints are public. Restrict network access or add an authentication layer if your deployment requires protected data access.
- Keep the service-role key and admin secret in the deployment platform's secret store, not in source control.

## Project Structure

```text
app/
├── api/routes/        # Health, ingestion, sentiment, and zone endpoints
├── db/                # Supabase client
├── schemas/           # Request and response models
├── services/          # Data clients, scoring, ingestion, and zone logic
├── config.py          # Environment-based settings
└── main.py            # FastAPI application and scheduler lifecycle
```

## Related Documentation

See the [repository README](../README.md) for the complete project setup, including the frontend and database migration workflow.
