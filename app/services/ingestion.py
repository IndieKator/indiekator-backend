"""The single ingestion entry point for the API.

Serves both ``POST /api/admin/ingest`` and the 07:00 Asia/Jakarta scheduled job.
Writes ``fgi_snapshots`` through the FGI pipeline and rebuilds ``zone_periods``
from those snapshots.

This function owns the ``ingestion_runs`` bookkeeping. ``run_fgi_ingestion``
deliberately does not touch that table, so if it is ever called directly the
``last_ingestion`` value reported by ``GET /api/health`` will not advance.
"""

from datetime import datetime, timezone
from typing import Any

from supabase import Client

from app.db.supabase import get_supabase
from app.services.fgi_ingestion import run_fgi_ingestion
from app.services.zone_builder import build_zone_periods

# zone_periods.id is a uuid with no natural "match everything" filter in the
# Supabase client, so a never-issued sentinel is used to express "delete all".
_NEVER_USED_ID = "00000000-0000-0000-0000-000000000000"

_ZONE_SOURCE_COLUMNS = "week_date, sentiment, close_price"


def run_ingestion() -> dict[str, Any]:
    """Ingest weekly FGI snapshots and rebuild the zone log.

    Returns a payload shaped for ``IngestResponse``. Re-raises on failure after
    marking the run row failed, so the caller can surface the error.
    """
    supabase = get_supabase()
    run_id: str | None = None

    try:
        run_result = (
            supabase.table("ingestion_runs").insert({"status": "running"}).execute()
        )
        run_id = run_result.data[0]["id"]

        rows_upserted = run_fgi_ingestion()
        zone_count = _rebuild_zone_periods(supabase)

        supabase.table("ingestion_runs").update(
            {
                "status": "success",
                "rows_upserted": rows_upserted,
                "finished_at": _now(),
            }
        ).eq("id", run_id).execute()

        return {
            "status": "success",
            "rows_upserted": rows_upserted,
            "message": (
                f"Ingested {rows_upserted} weekly FGI snapshots and rebuilt "
                f"{zone_count} zone periods"
            ),
        }
    except Exception as exc:
        if run_id is not None:
            supabase.table("ingestion_runs").update(
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "finished_at": _now(),
                }
            ).eq("id", run_id).execute()
        raise


def _rebuild_zone_periods(supabase: Client) -> int:
    """Replace zone_periods with episodes derived from fgi_snapshots.

    The new rows are computed before anything is deleted, so a derivation
    failure leaves the existing table untouched. An empty derivation is treated
    as "nothing to say" and also leaves the table alone, rather than wiping it.

    The delete and the insert are two separate Supabase calls, so a crash
    between them can leave zone_periods empty. That state is self-healing:
    ingestion is idempotent and rebuilds from fgi_snapshots on every run, and
    ``GET /api/zones`` returns 404 in the meantime, which the frontend already
    renders as a retryable error state.
    """
    result = (
        supabase.table("fgi_snapshots")
        .select(_ZONE_SOURCE_COLUMNS)
        .order("week_date", desc=False)
        .execute()
    )

    periods = build_zone_periods(result.data or [])
    if not periods:
        return 0

    supabase.table("zone_periods").delete().neq("id", _NEVER_USED_ID).execute()
    supabase.table("zone_periods").insert(periods).execute()
    return len(periods)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
