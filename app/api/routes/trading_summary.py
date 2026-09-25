from datetime import date
from fastapi import APIRouter, HTTPException, Query

from app.schemas.trading_summary import (
    TradingDayCurrent,
    TradingSummaryResponse,
)
from app.services.trading_summary import (
    build_current_summary,
    fetch_latest_two_records,
    fetch_trading_history_paginated,
)

router = APIRouter(prefix="/trading-summary", tags=["trading-summary"])


@router.get("", response_model=TradingSummaryResponse)
def get_trading_summary(
    limit: int = Query(
        default=30, ge=5, le=100, description="Number of bars to return"
    ),
    before: date | None = Query(
        default=None, description="Cursor date to fetch older bars (date < before)"
    ),
) -> TradingSummaryResponse:
    """Trading summary snapshot plus paginated historical bars for chart viewing."""
    recent_two = fetch_latest_two_records()
    if not recent_two:
        raise HTTPException(
            status_code=404,
            detail="No trading summary data available. Run ingestion or import first.",
        )

    today = recent_two[0]
    yesterday = recent_two[1] if len(recent_two) > 1 else None
    current = build_current_summary(today, yesterday)

    before_str = before.isoformat() if before else None
    history, pagination = fetch_trading_history_paginated(
        limit=limit, before_date=before_str
    )

    return TradingSummaryResponse(
        current=current,
        history=history,
        pagination=pagination,
        updated_at=current.updated_at,
    )


@router.get("/current", response_model=TradingDayCurrent)
def get_current_trading_summary() -> TradingDayCurrent:
    """Latest day's trading snapshot with Day-over-Day delta and average trade size."""
    recent_two = fetch_latest_two_records()
    if not recent_two:
        raise HTTPException(
            status_code=404,
            detail="No trading summary data available. Run ingestion or import first.",
        )

    today = recent_two[0]
    yesterday = recent_two[1] if len(recent_two) > 1 else None
    return build_current_summary(today, yesterday)
