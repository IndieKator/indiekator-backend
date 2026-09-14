"""Response models shared across the API.

Replaces the former ``app.schemas.sentiment`` module. The V1 models it also
carried (``DailySentimentPoint``, ``CurrentSentimentResponse``, ``DeltaInfo``,
``HistoryResponse``, ``ComponentContribution``, ``BreakdownResponse``, and the
``RangeKey`` literal) were removed with the ``/api/sentiment/*`` router, which
was their only consumer.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

ZoneKey = Literal[
    "extreme_fear",
    "fear",
    "neutral",
    "greed",
    "extreme_greed",
]


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
