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
    ma_30: float
    ema_13: float | None
    distance_pct: float
    search_score: float
    trends_mean: float | None = None


class FgiHistoryPoint(BaseModel):
    date: date
    value: float
    close_price: float
    ma_30: float
    ema_13: float | None
    distance_pct: float
    search_score: float
    trends_mean: float | None = None


class FgiResponse(BaseModel):
    current: FgiCurrentResponse
    history: list[FgiHistoryPoint]
    updated_at: datetime
    is_stale: bool


class TrendSnapshotPoint(BaseModel):
    date: date
    index_name: str
    keyword: str
    score: float
    search_score: float | None = None
    fgi_score: float | None = None
    sentiment: str | None = None


class TrendAggregatePoint(BaseModel):
    date: date
    index_name: str
    keywords: list[str]
    trends_mean: float
    search_score: float
    fgi_score: float
    sentiment: str


class TrendHistoryResponse(BaseModel):
    index_name: str
    keywords: list[str]
    count: int
    data: list[TrendSnapshotPoint]
    aggregate: list[TrendAggregatePoint]


class TrendRefreshRequest(BaseModel):
    index_name: str = Field(default="ihsg", min_length=1, max_length=64)
    keywords: list[str] = Field(min_length=1, max_length=5)
    start_date: date | None = None
    end_date: date | None = None


class TrendRefreshResponse(BaseModel):
    index_name: str
    keywords: list[str]
    count: int


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
    ma_30: float
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


class FgiBriefResponse(BaseModel):
    """AI-generated plain-English weekly market brief."""

    date: date
    brief: str
    source: Literal["ollama", "fallback"]
    updated_at: datetime
    is_stale: bool


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
