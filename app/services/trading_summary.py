from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.db.supabase import get_supabase
from app.schemas.trading_summary import (
    TradingSummaryCurrentResponse,
    TradingSummaryPoint,
    TradingSummaryResponse,
)

_SUMMARY_COLUMNS = "date, volume, value_idr, frequency, volume_ma_20, frequency_ma_20, value_ma_20, updated_at"

TRADING_RANGE_DAYS: dict[str, int | None] = {
    "30d": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "all": None,
}


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _trading_query():
    return get_supabase().table("daily_trading_summary").select(_SUMMARY_COLUMNS)


def fetch_latest_trading_summary() -> dict[str, Any] | None:
    result = _trading_query().order("date", desc=True).limit(1).execute()
    return result.data[0] if result.data else None


def fetch_recent_trading_records(limit: int = 30) -> list[dict[str, Any]]:
    """Return the newest records first (descending)."""
    result = _trading_query().order("date", desc=True).limit(limit).execute()
    return result.data or []


def fetch_trading_summary_history(
    start_date: str | None = None,
) -> list[dict[str, Any]]:
    """Return historical records oldest first (ascending)."""
    query = _trading_query()
    if start_date is not None:
        query = query.gte("date", start_date)
    result = query.order("date", desc=False).execute()
    return result.data or []


def to_trading_point(row: dict[str, Any]) -> TradingSummaryPoint:
    return TradingSummaryPoint(
        date=date.fromisoformat(str(row["date"])),
        volume=int(row["volume"]),
        value_idr=float(row["value_idr"]),
        frequency=int(row["frequency"]),
        volume_ma_20=(
            float(row["volume_ma_20"]) if row.get("volume_ma_20") is not None else None
        ),
        frequency_ma_20=(
            float(row["frequency_ma_20"])
            if row.get("frequency_ma_20") is not None
            else None
        ),
        value_ma_20=(
            float(row["value_ma_20"]) if row.get("value_ma_20") is not None else None
        ),
    )


def compute_20d_metrics(
    latest: dict[str, Any], recent_rows_desc: list[dict[str, Any]]
) -> dict[str, float | None]:
    """Compute 20-day moving average and percentage deltas if not present in the record."""
    volume = float(latest["volume"])
    frequency = float(latest["frequency"])
    value_idr = float(latest["value_idr"])

    # If row already has pre-computed 20D MA, use it
    vol_ma = (
        float(latest["volume_ma_20"])
        if latest.get("volume_ma_20") is not None
        else None
    )
    freq_ma = (
        float(latest["frequency_ma_20"])
        if latest.get("frequency_ma_20") is not None
        else None
    )
    val_ma = (
        float(latest["value_ma_20"]) if latest.get("value_ma_20") is not None else None
    )

    # If not stored, calculate dynamically from the last 20 available trading days
    if (vol_ma is None or freq_ma is None or val_ma is None) and recent_rows_desc:
        window_rows = recent_rows_desc[:20]
        if len(window_rows) >= 5:  # Require at least 5 days for a meaningful sample
            if vol_ma is None:
                vol_ma = sum(float(r["volume"]) for r in window_rows) / len(window_rows)
            if freq_ma is None:
                freq_ma = sum(float(r["frequency"]) for r in window_rows) / len(
                    window_rows
                )
            if val_ma is None:
                val_ma = sum(float(r["value_idr"]) for r in window_rows) / len(
                    window_rows
                )

    def _calc_pct(current: float, ma: float | None) -> float | None:
        if ma is not None and ma > 0:
            return round(((current - ma) / ma) * 100, 2)
        return None

    return {
        "volume_ma_20": round(vol_ma, 2) if vol_ma is not None else None,
        "volume_vs_ma_20_pct": _calc_pct(volume, vol_ma),
        "frequency_ma_20": round(freq_ma, 2) if freq_ma is not None else None,
        "frequency_vs_ma_20_pct": _calc_pct(frequency, freq_ma),
        "value_ma_20": round(val_ma, 2) if val_ma is not None else None,
        "value_vs_ma_20_pct": _calc_pct(value_idr, val_ma),
    }


def build_current_summary_response(
    latest: dict[str, Any],
    recent_rows_desc: list[dict[str, Any]] | None = None,
) -> TradingSummaryCurrentResponse:
    recent = (
        recent_rows_desc
        if recent_rows_desc is not None
        else fetch_recent_trading_records(20)
    )
    metrics = compute_20d_metrics(latest, recent)

    updated_at_val = latest.get("updated_at")
    updated_at = (
        _parse_datetime(updated_at_val)
        if updated_at_val
        else datetime.now(timezone.utc)
    )

    return TradingSummaryCurrentResponse(
        date=date.fromisoformat(str(latest["date"])),
        volume=int(latest["volume"]),
        value_idr=float(latest["value_idr"]),
        frequency=int(latest["frequency"]),
        volume_ma_20=metrics["volume_ma_20"],
        volume_vs_ma_20_pct=metrics["volume_vs_ma_20_pct"],
        frequency_ma_20=metrics["frequency_ma_20"],
        frequency_vs_ma_20_pct=metrics["frequency_vs_ma_20_pct"],
        value_ma_20=metrics["value_ma_20"],
        value_vs_ma_20_pct=metrics["value_vs_ma_20_pct"],
        updated_at=updated_at,
    )


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
