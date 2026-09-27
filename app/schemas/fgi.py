from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.core import ZoneKey

RangeKey = Literal["3m", "6m", "1y", "all"]


class FgiCurrentResponse(BaseModel):
    date: date
    value: float
    sentiment: str
    close_price: float
    ma_125: float
    ema_13: float | None
    distance_pct: float
    search_score: float
    trends_mean: float | None = None
    trend_ihsg: float | None = None
    trend_idx_composite: float | None = None
    trend_indeks_harga_saham_gabungan: float | None = None


class FgiHistoryPoint(BaseModel):
    date: date
    value: float
    close_price: float
    ma_125: float
    ema_13: float | None
    distance_pct: float
    search_score: float
    trends_mean: float | None = None
    trend_ihsg: float | None = None
    trend_idx_composite: float | None = None
    trend_indeks_harga_saham_gabungan: float | None = None


class FgiResponse(BaseModel):
    current: FgiCurrentResponse
    history: list[FgiHistoryPoint]
    updated_at: datetime
    is_stale: bool


class FgiDelta(BaseModel):
    """Change in the index against earlier weeks.

    The index is weekly, so the comparisons are week-over-week rather than the
    day-over-day deltas the retired V1 endpoint reported. A field is null when
    there is not enough history to compute it.
    """

    vs_last_week: float | None = None
    vs_month_ago: float | None = None


class FgiCurrentDetailResponse(BaseModel):
    date: date
    value: float
    sentiment: str
    zone: ZoneKey
    zone_label: str
    summary: str
    close_price: float
    ma_125: float
    ema_13: float | None
    distance_pct: float
    price_score: float
    search_score: float
    trends_mean: float
    delta: FgiDelta
    updated_at: datetime
    is_stale: bool


class FgiHistoryResponse(BaseModel):
    range: RangeKey
    count: int
    data: list[FgiHistoryPoint]


class FgiComponent(BaseModel):
    """One weighted input to the index.

    ``contribution`` is ``value * weight``. Across all components the
    contributions sum to the reported index value.
    """

    name: str
    label: str
    value: float
    weight: float
    contribution: float
    description: str


class FgiBreakdownResponse(BaseModel):
    date: date
    value: float
    sentiment: str
    zone: ZoneKey
    zone_label: str
    components: list[FgiComponent]
    coming_soon: list[str] = Field(
        default_factory=lambda: [
            "Realized Volatility (YTD)",
            "Net Foreign Buy/Sell Flow",
            "Safe-Haven Spread (IHSG vs SBN 10Y)",
        ]
    )
