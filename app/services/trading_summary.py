from datetime import date, datetime, timezone
from typing import Any

from app.db.supabase import get_supabase
from app.schemas.trading_summary import (
    TradingDayChange,
    TradingDayCurrent,
    TradingDayPoint,
    TradingPaginationInfo,
)

_SUMMARY_COLUMNS = "date, volume, value_idr, frequency, updated_at"


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _trading_query():
    return get_supabase().table("daily_trading_summary").select(_SUMMARY_COLUMNS)


def fetch_latest_trading_summary() -> dict[str, Any] | None:
    result = _trading_query().order("date", desc=True).limit(1).execute()
    return result.data[0] if result.data else None


def fetch_latest_two_records() -> list[dict[str, Any]]:
    """Return the newest 2 records descending (today, yesterday)."""
    result = _trading_query().order("date", desc=True).limit(2).execute()
    return result.data or []


def compute_daily_change(
    today: dict[str, Any], yesterday: dict[str, Any] | None
) -> TradingDayChange:
    """Compute Day-over-Day percentage change vs the prior trading day."""
    if not yesterday:
        return TradingDayChange()

    def _pct(curr: float, prev: float) -> float | None:
        if prev > 0:
            return round(((curr - prev) / prev) * 100, 2)
        return None

    return TradingDayChange(
        volume_pct=_pct(float(today["volume"]), float(yesterday["volume"])),
        value_pct=_pct(float(today["value_idr"]), float(yesterday["value_idr"])),
        frequency_pct=_pct(float(today["frequency"]), float(yesterday["frequency"])),
    )


def to_trading_point(row: dict[str, Any]) -> TradingDayPoint:
    return TradingDayPoint(
        date=date.fromisoformat(str(row["date"])),
        volume=int(row["volume"]),
        value_idr=float(row["value_idr"]),
        frequency=int(row["frequency"]),
    )


def build_current_summary(
    today: dict[str, Any], yesterday: dict[str, Any] | None = None
) -> TradingDayCurrent:
    frequency = int(today["frequency"])
    value_idr = float(today["value_idr"])
    avg_trade_size = round(value_idr / frequency, 2) if frequency > 0 else 0.0
    change = compute_daily_change(today, yesterday)

    updated_at_val = today.get("updated_at")
    updated_at = (
        _parse_datetime(updated_at_val)
        if updated_at_val
        else datetime.now(timezone.utc)
    )

    return TradingDayCurrent(
        date=date.fromisoformat(str(today["date"])),
        volume=int(today["volume"]),
        value_idr=value_idr,
        frequency=frequency,
        avg_trade_size=avg_trade_size,
        change=change,
        updated_at=updated_at,
    )


def fetch_trading_history_paginated(
    limit: int = 30, before_date: str | None = None
) -> tuple[list[TradingDayPoint], TradingPaginationInfo]:
    """Fetch trading records paginated chronologically (oldest first).

    Fetches limit + 1 records descending to detect if more historical data exists,
    then reverses them for chart display.
    """
    query = _trading_query()
    if before_date:
        query = query.lt("date", before_date)

    result = query.order("date", desc=True).limit(limit + 1).execute()
    rows = result.data or []

    has_more = len(rows) > limit
    target_rows = rows[:limit]
    # Reverse so the returned history is ascending (chronological)
    target_rows.reverse()

    points = [to_trading_point(r) for r in target_rows]
    oldest_date = points[0].date if points else None
    newest_date = points[-1].date if points else None

    pagination = TradingPaginationInfo(
        limit=limit,
        has_more=has_more,
        oldest_date=oldest_date,
        newest_date=newest_date,
    )
    return points, pagination


def upsert_trading_records(records: list[dict[str, Any]]) -> int:
    """Upsert trading records into Supabase daily_trading_summary table."""
    if not records:
        return 0

    supabase = get_supabase()
    result = (
        supabase.table("daily_trading_summary")
        .upsert(
            records,
            on_conflict="date",
        )
        .execute()
    )
    return len(result.data or records)
