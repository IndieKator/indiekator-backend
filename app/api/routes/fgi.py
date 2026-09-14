from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.supabase import get_supabase
from app.schemas.fgi import FgiCurrentResponse, FgiHistoryPoint, FgiResponse
from app.services.fgi_ingestion import run_fgi_ingestion

router = APIRouter(prefix="/fgi", tags=["fgi"])

STALE_AFTER = timedelta(hours=24)
HISTORY_DAYS = 183
_refresh_lock = Lock()


def _parse_updated_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


_SNAPSHOT_COLUMNS = "week_date, fgi, sentiment, close_price, ma_125, distance_pct, search_score, updated_at"


def _fetch_latest_snapshot() -> dict[str, Any] | None:
    result = (
        get_supabase()
        .table("fgi_snapshots")
        .select(_SNAPSHOT_COLUMNS)
        .order("week_date", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _is_stale(snapshot: dict[str, Any] | None) -> bool:
    if snapshot is None:
        return True
    return datetime.now(timezone.utc) - _parse_updated_at(snapshot["updated_at"]) > STALE_AFTER


def _refresh_if_stale() -> None:
    with _refresh_lock:
        if _is_stale(_fetch_latest_snapshot()):
            run_fgi_ingestion()


def _build_response(is_stale: bool) -> FgiResponse:
    latest = _fetch_latest_snapshot()
    if latest is None:
        raise HTTPException(status_code=503, detail="FGI data unavailable")

    start_date = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
    result = (
        get_supabase()
        .table("fgi_snapshots")
        .select(_SNAPSHOT_COLUMNS)
        .gte("week_date", start_date)
        .order("week_date", desc=False)
        .execute()
    )
    history = [
        FgiHistoryPoint(
            date=date.fromisoformat(row["week_date"]),
            value=float(row["fgi"]),
            close_price=float(row["close_price"]),
            ma_125=float(row["ma_125"]),
            distance_pct=float(row["distance_pct"]),
            search_score=float(row["search_score"]),
        )
        for row in (result.data or [])
    ]
    return FgiResponse(
        current=FgiCurrentResponse(
            date=date.fromisoformat(latest["week_date"]),
            value=float(latest["fgi"]),
            sentiment=latest["sentiment"],
            close_price=float(latest["close_price"]),
            ma_125=float(latest["ma_125"]),
            distance_pct=float(latest["distance_pct"]),
            search_score=float(latest["search_score"]),
        ),
        history=history,
        updated_at=_parse_updated_at(latest["updated_at"]),
        is_stale=is_stale,
    )


@router.get("", response_model=FgiResponse)
def get_fgi() -> FgiResponse:
    latest = _fetch_latest_snapshot()
    if not _is_stale(latest):
        return _build_response(is_stale=False)

    try:
        _refresh_if_stale()
    except Exception:
        if latest is None:
            raise HTTPException(status_code=503, detail="FGI data unavailable") from None
        return _build_response(is_stale=True)

    return _build_response(is_stale=False)
