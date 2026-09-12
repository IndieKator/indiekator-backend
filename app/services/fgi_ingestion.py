from app.db.supabase import get_supabase
from app.services.fgi_engine import compute_fgi, fgi_to_records


def run_fgi_ingestion() -> int:
    records = fgi_to_records(compute_fgi())
    if not records:
        raise RuntimeError("FGI calculation produced no snapshots")

    get_supabase().table("fgi_snapshots").upsert(
        records,
        on_conflict="week_date",
    ).execute()
    return len(records)
