from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase
from app.schemas.sentiment import (
    BreakdownResponse,
    ComponentContribution,
    CurrentSentimentResponse,
    DailySentimentPoint,
    DeltaInfo,
    HistoryResponse,
    RangeKey,
)
from app.services.zones import (
    build_summary,
    compute_breakdown_components,
    score_to_zone,
)

router = APIRouter(prefix="/sentiment", tags=["sentiment"])

RANGE_DAYS: dict[str, int | None] = {
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "all": None,
}


def _parse_row(row: dict[str, Any]) -> DailySentimentPoint:
    return DailySentimentPoint(
        date=date.fromisoformat(row["date"]),
        close_price=float(row["close_price"]),
        ma_125=float(row["ma_125"]) if row.get("ma_125") is not None else None,
        google_trends_raw=row.get("google_trends_raw"),
        normalized_trends=float(row["normalized_trends"])
        if row.get("normalized_trends") is not None
        else None,
        arah_momentum=row.get("arah_momentum"),
        skala_emosi=float(row["skala_emosi"]) if row.get("skala_emosi") is not None else None,
        zone=row["zone"],
    )


def _fetch_latest_rows(limit: int = 10) -> list[dict]:
    supabase = get_supabase()
    result = (
        supabase.table("daily_sentiment")
        .select("*")
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@router.get("/current", response_model=CurrentSentimentResponse)
def get_current_sentiment() -> CurrentSentimentResponse:
    rows = _fetch_latest_rows(10)
    if not rows:
        raise HTTPException(status_code=404, detail="No sentiment data available. Run ingestion first.")

    latest = rows[0]
    skala = float(latest["skala_emosi"])
    zone_key, zone_label = score_to_zone(skala)
    arah = int(latest["arah_momentum"])
    normalized = float(latest["normalized_trends"])

    delta = DeltaInfo()
    if len(rows) >= 2:
        delta.vs_yesterday = round(skala - float(rows[1]["skala_emosi"]), 2)
    if len(rows) >= 8:
        delta.vs_week_ago = round(skala - float(rows[7]["skala_emosi"]), 2)

    updated_at = latest.get("updated_at")
    last_updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else None
    trends_stale = last_updated is not None and (datetime.now(last_updated.tzinfo) - last_updated).days > 7

    return CurrentSentimentResponse(
        date=date.fromisoformat(latest["date"]),
        skala_emosi=skala,
        zone=zone_key,
        zone_label=zone_label,
        summary=build_summary(zone_label, arah, normalized),
        close_price=float(latest["close_price"]),
        ma_125=float(latest["ma_125"]),
        arah_momentum=arah,
        normalized_trends=normalized,
        delta=delta,
        last_updated=last_updated,
        trends_stale=trends_stale,
    )


@router.get("/history", response_model=HistoryResponse)
def get_history(
    range: RangeKey = Query(default="1y", alias="range"),
) -> HistoryResponse:
    supabase = get_supabase()
    query = supabase.table("daily_sentiment").select("*").order("date", desc=False)

    days = RANGE_DAYS[range]
    if days is not None:
        start = (datetime.now().date() - timedelta(days=days)).isoformat()
        query = query.gte("date", start)

    result = query.execute()
    data = [_parse_row(r) for r in (result.data or [])]
    return HistoryResponse(range=range, data=data)


@router.get("/breakdown", response_model=BreakdownResponse)
def get_breakdown() -> BreakdownResponse:
    rows = _fetch_latest_rows(1)
    if not rows:
        raise HTTPException(status_code=404, detail="No sentiment data available.")

    latest = rows[0]
    skala = float(latest["skala_emosi"])
    zone_key, zone_label = score_to_zone(skala)
    arah = int(latest["arah_momentum"])
    normalized = float(latest["normalized_trends"])

    components = [
        ComponentContribution(**c)
        for c in compute_breakdown_components(normalized, arah, skala)
    ]

    return BreakdownResponse(
        date=date.fromisoformat(latest["date"]),
        skala_emosi=skala,
        zone=zone_key,
        zone_label=zone_label,
        components=components,
    )
