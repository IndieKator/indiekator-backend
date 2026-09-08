from datetime import datetime, timezone

from app.db.supabase import get_supabase
from app.services.sentiment_engine import compute_sentiment, sentiment_to_records
from app.services.zone_analyzer import detect_zone_periods


def run_ingestion(lookback_days: int = 365) -> dict:
    supabase = get_supabase()
    run_id = None

    try:
        run_result = (
            supabase.table("ingestion_runs")
            .insert({"status": "running"})
            .execute()
        )
        run_id = run_result.data[0]["id"]

        df = compute_sentiment(lookback_days)
        records = sentiment_to_records(df)

        supabase.table("daily_sentiment").upsert(records).execute()

        zone_periods = detect_zone_periods(records)
        supabase.table("zone_periods").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        if zone_periods:
            supabase.table("zone_periods").insert(zone_periods).execute()

        supabase.table("ingestion_runs").update(
            {
                "status": "success",
                "rows_upserted": len(records),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", run_id).execute()

        return {
            "status": "success",
            "rows_upserted": len(records),
            "message": f"Successfully ingested {len(records)} daily records",
        }
    except Exception as exc:
        if run_id:
            supabase.table("ingestion_runs").update(
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", run_id).execute()
        raise
