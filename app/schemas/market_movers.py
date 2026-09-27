from datetime import date, datetime

from pydantic import BaseModel


class MoverStock(BaseModel):
    """A single company appearing in a gainers/losers list."""

    symbol: str
    name: str
    last_close_price: float
    # Raw ratio from Sectors (e.g. 0.05 == +5%) preserved for the client, plus
    # a pre-computed percentage so the frontend does not have to guess the unit.
    price_change_ratio: float
    price_change_pct: float
    latest_close_date: date | None = None


class MoversPeriod(BaseModel):
    """Gainers and losers for one lookback period (e.g. ``7d``)."""

    period: str
    top_gainers: list[MoverStock] = []
    top_losers: list[MoverStock] = []


class MoversResponse(BaseModel):
    periods: list[MoversPeriod]
    updated_at: datetime
