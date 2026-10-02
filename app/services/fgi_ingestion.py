from datetime import date, datetime, timezone

from app.db.supabase import get_supabase
from app.services.fgi_engine import compute_fgi, fgi_to_records
from app.services.fgi_trends_client import (
    FGI_INDEX_NAME,
    fetch_google_trends,
    normalize_keywords,
    trend_to_records,
)


def upsert_trend_snapshots(
    keywords: list[str] | tuple[str, ...],
    start_date: date,
    end_date: date,
    index_name: str = FGI_INDEX_NAME,
) -> int:
    """Fetch selected Google Trends keywords and persist their long-form scores."""
    trends = fetch_google_trends(normalize_keywords(keywords), start_date, end_date)
    records = trend_to_records(trends, index_name=index_name)
    if not records:
        raise RuntimeError("Google Trends calculation produced no snapshots")

    get_supabase().table("trend_snapshots").upsert(
        records,
        on_conflict="date,index_name,keyword",
    ).execute()
    return len(records)


def run_fgi_ingestion() -> int:
    dataframe = compute_fgi()
    records = fgi_to_records(dataframe)
    if not records:
        raise RuntimeError("FGI calculation produced no snapshots")

    trend_records = trend_to_records(dataframe.attrs["trend_snapshots"])
    get_supabase().table("trend_snapshots").upsert(
        trend_records,
        on_conflict="date,index_name,keyword",
    ).execute()
    get_supabase().table("fgi_snapshots").upsert(
        records,
        on_conflict="week_date",
    ).execute()
    return len(records)
