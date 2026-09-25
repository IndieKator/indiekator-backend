from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas.trading_summary import (
    TradingRangeKey,
    TradingSummaryCurrentResponse,
    TradingSummaryHistoryResponse,
    TradingSummaryResponse,
)
from app.services.trading_summary import (
    TRADING_RANGE_DAYS,
    build_current_summary_response,
    fetch_latest_trading_summary,
    fetch_recent_trading_records,
    fetch_trading_summary_history,
    to_trading_point,
)

router = APIRouter(prefix="/trading-summary", tags=["trading-summary"])


@router.get("", response_model=TradingSummaryResponse)
def get_trading_summary() -> TradingSummaryResponse:
    """Latest trading summary snapshot plus historical points."""
    latest = fetch_latest_trading_summary()
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail="No trading summary data available. Run ingestion or import first.",
        )

    recent_rows = fetch_recent_trading_records(30)
    current = build_current_summary_response(latest, recent_rows)
    history_rows = fetch_trading_summary_history()
    points = [to_trading_point(row) for row in history_rows]

    return TradingSummaryResponse(
        current=current,
        history=points,
        updated_at=current.updated_at,
    )


@router.get("/current", response_model=TradingSummaryCurrentResponse)
def get_current_trading_summary() -> TradingSummaryCurrentResponse:
    """Latest day's trading volume, frequency, and turnover with 20D averages and deltas."""
    latest = fetch_latest_trading_summary()
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail="No trading summary data available. Run ingestion or import first.",
        )

    recent_rows = fetch_recent_trading_records(30)
    return build_current_summary_response(latest, recent_rows)


@router.get("/history", response_model=TradingSummaryHistoryResponse)
def get_trading_summary_history(
    range: TradingRangeKey = Query(default="30d", alias="range"),
    days: int | None = Query(
        default=None, ge=1, le=1825, description="Custom number of days"
    ),
) -> TradingSummaryHistoryResponse:
    """Historical trading summary points (volume, frequency, turnover)."""
    filter_days = days if days is not None else TRADING_RANGE_DAYS[range]
    start_date = None
    if filter_days is not None:
        start_date = (date.today() - timedelta(days=filter_days)).isoformat()

    rows = fetch_trading_summary_history(start_date)
    points = [to_trading_point(row) for row in rows]

    range_label = f"{days}d" if days is not None else range
    return TradingSummaryHistoryResponse(
        range=range_label,
        count=len(points),
        data=points,
    )
