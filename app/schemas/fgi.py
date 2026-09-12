from datetime import date, datetime

from pydantic import BaseModel


class FgiCurrentResponse(BaseModel):
    date: date
    value: float
    sentiment: str


class FgiHistoryPoint(BaseModel):
    date: date
    value: float


class FgiResponse(BaseModel):
    current: FgiCurrentResponse
    history: list[FgiHistoryPoint]
    updated_at: datetime
    is_stale: bool
