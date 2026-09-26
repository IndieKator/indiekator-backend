from datetime import date, datetime
from pydantic import BaseModel


class TradingDayChange(BaseModel):
    volume_pct: float | None = None
    value_pct: float | None = None
    frequency_pct: float | None = None


class TradingDayPoint(BaseModel):
    date: date
    volume: int
    value_idr: float
    frequency: int


class TradingDayCurrent(BaseModel):
    date: date
    volume: int
    value_idr: float
    frequency: int
    avg_trade_size: float
    change: TradingDayChange
    updated_at: datetime


class TradingPaginationInfo(BaseModel):
    limit: int
    has_more: bool
    oldest_date: date | None = None
    newest_date: date | None = None


class TradingSummaryResponse(BaseModel):
    current: TradingDayCurrent
    history: list[TradingDayPoint]
    pagination: TradingPaginationInfo
    updated_at: datetime


# Aliases for backward compatibility
TradingSummaryPoint = TradingDayPoint
TradingSummaryCurrentResponse = TradingDayCurrent
