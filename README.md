# IndieKator Backend

FastAPI service for IHSG Fear & Greed Index computation and API.

## Quick Start

```bash
cp .env.example .env
# Fill in SECTORS_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ADMIN_SECRET

pip install -e .
uvicorn app.main:app --reload --port 8000
```

## First Ingest

```bash
curl -X POST http://localhost:8000/api/admin/ingest -H "X-Admin-Secret: YOUR_SECRET"
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

See root [README.md](../README.md) for full documentation.
