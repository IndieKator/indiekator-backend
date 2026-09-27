import httpx
from fastapi import APIRouter, HTTPException, Query

from app.schemas.market_movers import MoversResponse
from app.services.market_movers import get_top_movers

router = APIRouter(prefix="/market-movers", tags=["market-movers"])

_ALLOWED_PERIODS = {"1d", "7d", "14d", "30d", "365d"}


@router.get("", response_model=MoversResponse)
def get_market_movers(
    periods: str = Query(
        default="7d",
        description="Comma-separated lookback periods: 1d, 7d, 14d, 30d, 365d",
    ),
    n_stock: int = Query(default=5, ge=1, le=10, description="Stocks per list"),
    min_mcap_billion: int = Query(
        default=5000, ge=0, description="Minimum market cap in billion IDR"
    ),
) -> MoversResponse:
    """Top gainers and losers on IDX, sourced live from the Sectors API."""
    requested = [p.strip() for p in periods.split(",") if p.strip()]
    invalid = [p for p in requested if p not in _ALLOWED_PERIODS]
    if not requested or invalid:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid periods {invalid or requested}. "
                f"Allowed: {sorted(_ALLOWED_PERIODS)}"
            ),
        )

    try:
        return get_top_movers(
            periods=",".join(requested),
            n_stock=n_stock,
            min_mcap_billion=min_mcap_billion,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Sectors API error: {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Sectors API is unreachable"
        ) from exc
