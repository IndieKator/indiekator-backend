from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase
from app.schemas.fgi import (
    FgiBreakdownResponse,
    FgiComponent,
    FgiCurrentDetailResponse,
    FgiCurrentResponse,
    FgiDelta,
    FgiHistoryPoint,
    FgiHistoryResponse,
    FgiResponse,
    RangeKey,
)
from app.services.ingestion import run_ingestion
from app.services.fgi_presentation import (
    build_components,
    build_summary,
    zone_for_sentiment,
)

router = APIRouter(prefix="/fgi", tags=["fgi"])

STALE_AFTER = timedelta(hours=24)
_refresh_lock = Lock()

RANGE_DAYS: dict[str, int | None] = {
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "all": None,
}

# Number of weekly snapshots back that the "vs month ago" delta compares against.
_WEEKS_PER_MONTH = 4

_SNAPSHOT_COLUMNS = (
    "week_date, fgi, sentiment, close_price, ma_125, distance_pct, "
    "price_score, search_score, trends_mean, updated_at"
)


def _parse_updated_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _snapshot_query():
    return get_supabase().table("fgi_snapshots").select(_SNAPSHOT_COLUMNS)


def _fetch_latest_snapshot() -> dict[str, Any] | None:
    result = _snapshot_query().order("week_date", desc=True).limit(1).execute()
    return result.data[0] if result.data else None


def _fetch_recent_snapshots(limit: int) -> list[dict[str, Any]]:
    """Return the newest snapshots first."""
    result = _snapshot_query().order("week_date", desc=True).limit(limit).execute()
    return result.data or []


def _fetch_snapshots_since(start: str | None) -> list[dict[str, Any]]:
    """Return snapshots oldest first, optionally bounded below by ``start``."""
    query = _snapshot_query()
    if start is not None:
        query = query.gte("week_date", start)
    result = query.order("week_date", desc=False).execute()
    return result.data or []


def _is_stale(snapshot: dict[str, Any] | None) -> bool:
    if snapshot is None:
        return True
    return datetime.now(timezone.utc) - _parse_updated_at(snapshot["updated_at"]) > STALE_AFTER


def _refresh_if_stale() -> None:
    with _refresh_lock:
        if _is_stale(_fetch_latest_snapshot()):
            run_ingestion()


def _resolve_snapshot() -> tuple[dict[str, Any], bool]:
    """Return the newest snapshot plus whether it is being served stale.

    Refreshes when the newest snapshot has aged past ``STALE_AFTER``. If that
    refresh fails, an existing snapshot is served with the stale flag set;
    without one there is nothing to serve, so the caller gets a 503.
    """
    latest = _fetch_latest_snapshot()
    if not _is_stale(latest):
        return latest, False

    try:
        _refresh_if_stale()
    except Exception:
        if latest is None:
            raise HTTPException(status_code=503, detail="FGI data unavailable") from None
        return latest, True

    refreshed = _fetch_latest_snapshot()
    if refreshed is None:
        raise HTTPException(status_code=503, detail="FGI data unavailable")
    return refreshed, False


def _to_history_point(row: dict[str, Any]) -> FgiHistoryPoint:
    return FgiHistoryPoint(
        date=date.fromisoformat(row["week_date"]),
        value=float(row["fgi"]),
        close_price=float(row["close_price"]),
        ma_125=float(row["ma_125"]),
        distance_pct=float(row["distance_pct"]),
        search_score=float(row["search_score"]),
    )


def _build_response(latest: dict[str, Any], is_stale: bool) -> FgiResponse:
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
        history=[_to_history_point(row) for row in _fetch_snapshots_since(None)],
        updated_at=_parse_updated_at(latest["updated_at"]),
        is_stale=is_stale,
    )


@router.get("", response_model=FgiResponse)
def get_fgi() -> FgiResponse:
    """Latest snapshot plus the full weekly history.

    Returns every snapshot rather than a fixed trailing window. A window here
    would cap what the client can show no matter what range it asks for, which
    is what previously pinned the chart's earliest point to roughly six months
    back. Callers wanting a narrower slice use ``/api/fgi/history``.
    """
    latest, is_stale = _resolve_snapshot()
    return _build_response(latest, is_stale)


@router.get("/current", response_model=FgiCurrentDetailResponse)
def get_current_fgi() -> FgiCurrentDetailResponse:
    """Latest index value with its zone, summary, market values, and deltas."""
    latest, is_stale = _resolve_snapshot()

    rows = _fetch_recent_snapshots(_WEEKS_PER_MONTH + 1)
    value = float(latest["fgi"])
    distance_pct = float(latest["distance_pct"])
    search_score = float(latest["search_score"])
    zone_key, zone_label = zone_for_sentiment(latest["sentiment"])

    delta = FgiDelta()
    if len(rows) >= 2:
        delta.vs_last_week = round(value - float(rows[1]["fgi"]), 2)
    if len(rows) > _WEEKS_PER_MONTH:
        delta.vs_month_ago = round(value - float(rows[_WEEKS_PER_MONTH]["fgi"]), 2)

    return FgiCurrentDetailResponse(
        date=date.fromisoformat(latest["week_date"]),
        value=value,
        sentiment=latest["sentiment"],
        zone=zone_key,
        zone_label=zone_label,
        summary=build_summary(zone_label, distance_pct, search_score),
        close_price=float(latest["close_price"]),
        ma_125=float(latest["ma_125"]),
        distance_pct=distance_pct,
        price_score=float(latest["price_score"]),
        search_score=search_score,
        trends_mean=float(latest["trends_mean"]),
        delta=delta,
        updated_at=_parse_updated_at(latest["updated_at"]),
        is_stale=is_stale,
    )


@router.get("/history", response_model=FgiHistoryResponse)
def get_fgi_history(
    range: RangeKey = Query(default="1y", alias="range"),
) -> FgiHistoryResponse:
    """Weekly snapshots over the requested window, oldest first."""
    _resolve_snapshot()

    days = RANGE_DAYS[range]
    start = None if days is None else (date.today() - timedelta(days=days)).isoformat()
    points = [_to_history_point(row) for row in _fetch_snapshots_since(start)]

    return FgiHistoryResponse(range=range, count=len(points), data=points)


@router.get("/breakdown", response_model=FgiBreakdownResponse)
def get_fgi_breakdown() -> FgiBreakdownResponse:
    """Latest index value split into its weighted components."""
    latest, _ = _resolve_snapshot()
    zone_key, zone_label = zone_for_sentiment(latest["sentiment"])

    components = build_components(
        price_score=float(latest["price_score"]),
        search_score=float(latest["search_score"]),
        distance_pct=float(latest["distance_pct"]),
    )

    return FgiBreakdownResponse(
        date=date.fromisoformat(latest["week_date"]),
        value=float(latest["fgi"]),
        sentiment=latest["sentiment"],
        zone=zone_key,
        zone_label=zone_label,
        components=[FgiComponent(**component) for component in components],
    )
