from datetime import date
from fastapi import APIRouter, HTTPException, Query

from app.schemas.trading_summary import (
    TradingDayCurrent,
    TradingSummaryResponse,
)
from app.services.trading_summary import (
    build_current_summary,
    fetch_trading_history_paginated,
)
from app.services.trading_summary_repository import (
    fetch_latest_two_records,
    fetch_sync_state,
)
from app.services.trading_summary_sync import (
    TradingSummaryNotFoundError,
    TradingSummaryUnavailableError,
    sync_trading_summary_on_demand,
)

router = APIRouter(prefix="/trading-summary", tags=["trading-summary"])


def _current_summary() -> TradingDayCurrent:
    try:
        is_stale = sync_trading_summary_on_demand()
    except TradingSummaryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No trading summary data available") from exc
    except TradingSummaryUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Trading summary data unavailable") from exc

    recent_two = fetch_latest_two_records()
    if not recent_two:
        raise HTTPException(status_code=404, detail="No trading summary data available")
    latest = recent_two[0]
    state = fetch_sync_state(date.fromisoformat(str(latest["date"])))
    return build_current_summary(
        latest,
        recent_two[1] if len(recent_two) > 1 else None,
        is_final=bool(state and state.get("finalized_at")),
        is_stale=is_stale,
    )


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
    current = _current_summary()

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
    return _current_summary()
