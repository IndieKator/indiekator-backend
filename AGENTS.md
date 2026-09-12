# Repository Guidelines

## Project Structure & Module Organization

The FastAPI application lives in `app/`. Keep endpoints in `app/api/routes/`, models in `app/schemas/`, business and ingestion logic in `app/services/`, and Supabase setup in `app/db/`. `app/main.py` creates the app, registers routes, and starts daily ingestion; `app/config.py` owns environment-backed settings. `delete-later/` contains exploratory notebooks, not application code. There is no committed test suite; add tests under `tests/` using the same module-oriented structure.

## Build, Test, and Development Commands

- `uv sync` installs the locked Python 3.12+ environment from `pyproject.toml` and `uv.lock`.
- `Copy-Item .env.example .env` creates local configuration; fill in the required API and Supabase credentials.
- `uv run uvicorn app.main:app --reload --port 8000` runs the API locally with reload. `uv run indiekator` runs the packaged development entry point.
- `curl -X POST http://localhost:8000/api/admin/ingest -H "X-Admin-Secret: YOUR_SECRET"` triggers an initial ingestion after configuration.
- `uv run pytest` runs tests once added; introduce it as an explicit development dependency.

## Coding Style & Naming Conventions

Use Python with four-space indentation, standard import grouping, and type annotations for public functions. Use `snake_case` for modules, functions, variables, and API fields; use `PascalCase` for Pydantic models. Keep route handlers thin: place transformations, external requests, and ingestion in services. Declare endpoint response models and preserve the `/api` router prefix. No formatter or linter is configured; avoid unrelated reformatting and match nearby code.

## Testing Guidelines

Use `pytest`; name files `test_<module>.py` and tests `test_<behavior>`. Unit-test scoring, zone detection, and record conversion without network calls; mock Supabase and external-data clients for routes and ingestion. Cover normal output, empty data, and rejected admin secrets. Run the full suite before a pull request.

## Commit & Pull Request Guidelines

The history uses short imperative subjects (`Init project`); continue with messages such as `Add sentiment history validation`. Keep commits focused. Pull requests should explain behavior changes, list configuration or schema impacts, link related issues, and include example request/response output for API changes.

## Security & Configuration

Never commit `.env` or credentials. `SUPABASE_SERVICE_ROLE_KEY` is server-only and must not be exposed to browser code or logs. Change `ADMIN_SECRET` from its example value, restrict `CORS_ORIGINS` for deployed environments, and avoid printing secrets in errors or test fixtures.
