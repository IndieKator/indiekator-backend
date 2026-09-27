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
from app.services.ollama_client import generate_market_brief
from app.schemas.fgi import FgiBriefResponse

router = APIRouter(prefix="/fgi", tags=["fgi"])

STALE_AFTER = timedelta(hours=24)
# The AI brief is reused for a day; a fresh close price busts it earlier.
BRIEF_TTL = timedelta(hours=24)
_refresh_lock = Lock()
_brief_lock = Lock()

RANGE_DAYS: dict[str, int | None] = {
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "all": None,
}

# Number of weekly snapshots back that the "vs month ago" delta compares against.
_WEEKS_PER_MONTH = 4

# Window for the "EMA 20" the dashboard reports; kept in sync with the
# frontend's MA_WINDOW so the brief describes the same line the chart draws.
_EMA_WINDOW = 20

_SNAPSHOT_COLUMNS = (
    "week_date, fgi, sentiment, close_price, ma_30, ema_13, distance_pct, "
    "price_score, search_score, trends_mean, trend_ihsg, trend_idx_composite, "
    "trend_indeks_harga_saham_gabungan, updated_at"
)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


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
        ma_30=float(row["ma_30"]),
        ema_13=_optional_float(row.get("ema_13")),
        distance_pct=float(row["distance_pct"]),
        search_score=float(row["search_score"]),
        trends_mean=_optional_float(row.get("trends_mean")),
        trend_ihsg=_optional_float(row.get("trend_ihsg")),
        trend_idx_composite=_optional_float(row.get("trend_idx_composite")),
        trend_indeks_harga_saham_gabungan=_optional_float(
            row.get("trend_indeks_harga_saham_gabungan")
        ),
    )


def _build_response(latest: dict[str, Any], is_stale: bool) -> FgiResponse:
    return FgiResponse(
        current=FgiCurrentResponse(
            date=date.fromisoformat(latest["week_date"]),
            value=float(latest["fgi"]),
            sentiment=latest["sentiment"],
            close_price=float(latest["close_price"]),
            ma_30=float(latest["ma_30"]),
            ema_13=_optional_float(latest.get("ema_13")),
            distance_pct=float(latest["distance_pct"]),
            search_score=float(latest["search_score"]),
            trends_mean=_optional_float(latest.get("trends_mean")),
            trend_ihsg=_optional_float(latest.get("trend_ihsg")),
            trend_idx_composite=_optional_float(latest.get("trend_idx_composite")),
            trend_indeks_harga_saham_gabungan=_optional_float(
                latest.get("trend_indeks_harga_saham_gabungan")
            ),
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
        ma_30=float(latest["ma_30"]),
        ema_13=_optional_float(latest.get("ema_13")),
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


def _ema(values: list[float], period: int) -> float | None:
    """EMA over the trailing ``period`` closes, seeded on the window's first value.

    Mirrors the frontend ``emaAt`` so the brief's "EMA 20" matches the chart.
    Returns ``None`` when there aren't enough points to fill the window.
    """
    if len(values) < period:
        return None
    window = values[-period:]
    multiplier = 2 / (period + 1)
    ema = window[0]
    for value in window[1:]:
        ema = value * multiplier + ema * (1 - multiplier)
    return ema


def _brief_facts(latest: dict[str, Any]) -> dict[str, Any]:
    """Assemble the figures the brief describes from recent snapshots.

    Week-over-week change and the EMA-20 distance are derived from the newest
    snapshots so they line up with what the dashboard's General tab renders.
    """
    close = float(latest["close_price"])

    # Oldest-first closes covering enough history to seed the 20-week EMA.
    recent = _fetch_recent_snapshots(_EMA_WINDOW + 1)
    closes = [float(row["close_price"]) for row in reversed(recent)]

    change_pct = 0.0
    if len(recent) >= 2:
        prev_close = float(recent[1]["close_price"])
        if prev_close:
            change_pct = (close - prev_close) / prev_close * 100

    ema20 = _ema(closes, _EMA_WINDOW)
    distance_pct = (
        (close - ema20) / ema20 * 100
        if ema20
        else float(latest["distance_pct"])
    )

    return {
        "close_price": close,
        "change_pct": change_pct,
        "distance_pct": distance_pct,
        "fgi": round(float(latest["fgi"])),
        "sentiment": latest["sentiment"],
    }


def _generate_brief(facts: dict[str, Any]) -> tuple[str, str]:
    """Return ``(brief, source)``, calling Ollama with a template fallback.

    The deterministic fallback mirrors the model's expected style so the UI
    stays coherent when the key is missing or the call fails.
    """
    try:
        return generate_market_brief(facts), "ollama"
    except Exception:
        direction = "up" if facts["change_pct"] >= 0 else "down"
        position = "above" if facts["distance_pct"] >= 0 else "below"
        brief = (
            f"IHSG closed at {facts['close_price']:,.2f}, {direction} "
            f"{facts['change_pct']:+.2f}% on the week and trading {position} "
            f"its EMA 20. The Fear & Greed Index reads {facts['fgi']} "
            f"({facts['sentiment']})."
        )
        return brief, "fallback"


def _fetch_cached_brief(week_date: str) -> dict[str, Any] | None:
    result = (
        get_supabase()
        .table("ai_brief_cache")
        .select("week_date, brief, close_price, source, generated_at")
        .eq("week_date", week_date)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _cache_is_fresh(cached: dict[str, Any], close_price: float) -> bool:
    """A cache row is reusable while it describes the current close and is <1 day old.

    A changed ``close_price`` means new IHSG data, so the brief is regenerated
    even within the day; otherwise it is reused until the TTL lapses.
    """
    if abs(float(cached["close_price"]) - close_price) > 1e-9:
        return False
    age = datetime.now(timezone.utc) - _parse_updated_at(cached["generated_at"])
    return age < BRIEF_TTL


def _store_brief(
    week_date: str, brief: str, close_price: float, source: str
) -> None:
    get_supabase().table("ai_brief_cache").upsert(
        {
            "week_date": week_date,
            "brief": brief,
            "close_price": close_price,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="week_date",
    ).execute()


@router.get("/brief", response_model=FgiBriefResponse)
def get_fgi_brief() -> FgiBriefResponse:
    """AI market brief for the latest snapshot, cached for a day.

    Serves the stored brief for the current week's snapshot until it is a day
    old or the IHSG close price changes, at which point it regenerates via
    Ollama Cloud. Falls back to a deterministic sentence if the model call
    fails or no key is configured, so the dashboard always has something to
    show.
    """
    latest, is_stale = _resolve_snapshot()
    week_date = latest["week_date"]
    close_price = float(latest["close_price"])
    updated_at = _parse_updated_at(latest["updated_at"])

    cached = _fetch_cached_brief(week_date)
    if cached and _cache_is_fresh(cached, close_price):
        return FgiBriefResponse(
            date=date.fromisoformat(week_date),
            brief=cached["brief"],
            source=cached["source"],
            updated_at=updated_at,
            is_stale=is_stale,
        )

    # Serialize regeneration so a burst of first-load requests triggers one
    # Ollama call rather than one per request; re-check the cache inside.
    with _brief_lock:
        cached = _fetch_cached_brief(week_date)
        if cached and _cache_is_fresh(cached, close_price):
            brief, source = cached["brief"], cached["source"]
        else:
            brief, source = _generate_brief(_brief_facts(latest))
            try:
                _store_brief(week_date, brief, close_price, source)
            except Exception:
                # A cache write failure shouldn't fail the request; the brief
                # is still returned and will simply be regenerated next time.
                pass

    return FgiBriefResponse(
        date=date.fromisoformat(week_date),
        brief=brief,
        source=source,
        updated_at=updated_at,
        is_stale=is_stale,
    )
