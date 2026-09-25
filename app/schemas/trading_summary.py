from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TradingRangeKey = Literal["30d", "3m", "6m", "1y", "all"]


class TradingSummaryPoint(BaseModel):
    date: date
    volume: int
    value_idr: float
    frequency: int
    volume_ma_20: float | None = None
    frequency_ma_20: float | None = None
    value_ma_20: float | None = None


class TradingSummaryCurrentResponse(BaseModel):
    date: date
    volume: int
    value_idr: float
    frequency: int
    volume_ma_20: float | None = None
    volume_vs_ma_20_pct: float | None = None
    frequency_ma_20: float | None = None
    frequency_vs_ma_20_pct: float | None = None
    value_ma_20: float | None = None
    value_vs_ma_20_pct: float | None = None
    updated_at: datetime


class TradingSummaryHistoryResponse(BaseModel):
    range: str
    count: int
    data: list[TradingSummaryPoint]


class TradingSummaryResponse(BaseModel):
    current: TradingSummaryCurrentResponse
    history: list[TradingSummaryPoint]
    updated_at: datetime
