from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ZoneKey = Literal[
    "extreme_fear",
    "fear",
    "neutral",
    "greed",
    "extreme_greed",
]

RangeKey = Literal["3m", "6m", "1y", "all"]


class DailySentimentPoint(BaseModel):
    date: date
    close_price: float
    ma_125: float | None = None
    google_trends_raw: int | None = None
    normalized_trends: float | None = None
    arah_momentum: int | None = None
    skala_emosi: float | None = None
    zone: str


class DeltaInfo(BaseModel):
    vs_yesterday: float | None = None
    vs_week_ago: float | None = None


class CurrentSentimentResponse(BaseModel):
    date: date
    skala_emosi: float
    zone: ZoneKey
    zone_label: str
    summary: str
    close_price: float
    ma_125: float
    arah_momentum: int
    normalized_trends: float
    delta: DeltaInfo
    last_updated: datetime | None = None
    trends_stale: bool = False


class HistoryResponse(BaseModel):
    range: RangeKey
    data: list[DailySentimentPoint]


class ComponentContribution(BaseModel):
    name: str
    label: str
    value: float
    description: str


class BreakdownResponse(BaseModel):
    date: date
    skala_emosi: float
    zone: ZoneKey
    zone_label: str
    components: list[ComponentContribution]
    coming_soon: list[str] = Field(
        default_factory=lambda: [
            "Realized Volatility (YTD)",
            "Net Foreign Buy/Sell Flow",
            "Safe-Haven Spread (IHSG vs SBN 10Y)",
        ]
    )


class ZonePeriodResponse(BaseModel):
    id: str
    zone: ZoneKey
    zone_label: str
    entry_date: date
    exit_date: date | None
    duration_days: int | None
    return_pct: float | None
    is_active: bool


class HealthResponse(BaseModel):
    status: str
    last_ingestion: datetime | None = None


class IngestResponse(BaseModel):
    status: str
    rows_upserted: int
    message: str
