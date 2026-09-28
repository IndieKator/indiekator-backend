"""Supabase persistence for daily trading summaries and fetch state."""

from datetime import date, datetime
from typing import Any

from app.db.supabase import get_supabase

SUMMARY_COLUMNS = "date, volume, value_idr, frequency, updated_at"


def _summary_query():
    return get_supabase().table("daily_trading_summary").select(SUMMARY_COLUMNS)


def fetch_latest_trading_summary() -> dict[str, Any] | None:
    result = _summary_query().order("date", desc=True).limit(1).execute()
    return result.data[0] if result.data else None


def fetch_latest_two_records() -> list[dict[str, Any]]:
    result = _summary_query().order("date", desc=True).limit(2).execute()
    return result.data or []


def fetch_history_rows(limit: int, before_date: str | None) -> list[dict[str, Any]]:
    query = _summary_query()
    if before_date:
        query = query.lt("date", before_date)
    result = query.order("date", desc=True).limit(limit + 1).execute()
    return result.data or []


def upsert_trading_records(records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    result = (
        get_supabase()
        .table("daily_trading_summary")
        .upsert(records, on_conflict="date")
        .execute()
    )
    return len(result.data or records)


def fetch_sync_state(target_date: date) -> dict[str, Any] | None:
    result = (
        get_supabase()
        .table("trading_summary_sync_state")
        .select("date, last_attempt_at, finalized_at")
        .eq("date", target_date.isoformat())
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def save_sync_state(
    target_date: date, last_attempt_at: datetime, finalized_at: datetime | None = None
) -> None:
    get_supabase().table("trading_summary_sync_state").upsert(
        {
            "date": target_date.isoformat(),
            "last_attempt_at": last_attempt_at.isoformat(),
            "finalized_at": finalized_at.isoformat() if finalized_at else None,
        },
        on_conflict="date",
    ).execute()
