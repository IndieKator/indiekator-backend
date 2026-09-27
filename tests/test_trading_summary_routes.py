from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import trading_summary
from app.main import app
from app.services.trading_summary import (
    compute_daily_change,
    fetch_trading_history_paginated,
)


@pytest.fixture(autouse=True)
def _disable_live_sync(monkeypatch) -> None:
    monkeypatch.setattr(trading_summary, "sync_trading_summary_on_demand", lambda: False)
    monkeypatch.setattr(trading_summary, "fetch_sync_state", lambda _date: None)


def _sample_trading_rows() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "date": "2026-08-28",
            "volume": 9_820_000_000,
            "value_idr": 12_400_000_000_000.0,
            "frequency": 1_280_000,
            "updated_at": now,
        },
        {
            "date": "2026-08-27",
            "volume": 8_500_000_000,
            "value_idr": 11_200_000_000_000.0,
            "frequency": 1_150_000,
            "updated_at": now,
        },
        {
            "date": "2026-08-26",
            "volume": 7_200_000_000,
            "value_idr": 10_100_000_000_000.0,
            "frequency": 1_000_000,
            "updated_at": now,
        },
    ]


def test_get_current_trading_summary(monkeypatch) -> None:
    rows = _sample_trading_rows()
    monkeypatch.setattr(trading_summary, "fetch_latest_two_records", lambda: rows[:2])

    response = TestClient(app).get("/api/trading-summary/current")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-08-28"
    assert data["volume"] == 9_820_000_000
    assert data["value_idr"] == 12_400_000_000_000.0
    assert data["frequency"] == 1_280_000
    # 12.4T / 1.28M trades = 9,687,500.0
    assert data["avg_trade_size"] == 9687500.0
    # Day-over-Day change
    assert data["change"]["volume_pct"] == 15.53
    assert data["change"]["value_pct"] == 10.71
    assert data["change"]["frequency_pct"] == 11.30


def test_get_current_trading_summary_single_day(monkeypatch) -> None:
    rows = _sample_trading_rows()
    # Only 1 day exists
    monkeypatch.setattr(trading_summary, "fetch_latest_two_records", lambda: [rows[0]])

    response = TestClient(app).get("/api/trading-summary/current")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-08-28"
    assert data["change"]["volume_pct"] is None
    assert data["change"]["value_pct"] is None
    assert data["change"]["frequency_pct"] is None


def test_current_exposes_final_and_stale_status(monkeypatch) -> None:
    rows = _sample_trading_rows()
    monkeypatch.setattr(trading_summary, "fetch_latest_two_records", lambda: rows[:2])
    monkeypatch.setattr(trading_summary, "sync_trading_summary_on_demand", lambda: True)
    monkeypatch.setattr(
        trading_summary,
        "fetch_sync_state",
        lambda _date: {"finalized_at": "2026-08-28T10:00:00Z"},
    )

    response = TestClient(app).get("/api/trading-summary/current")

    assert response.status_code == 200
    assert response.json()["is_final"] is True
    assert response.json()["is_stale"] is True


def test_get_current_trading_summary_404_when_empty(monkeypatch) -> None:
    monkeypatch.setattr(trading_summary, "fetch_latest_two_records", lambda: [])

    response = TestClient(app).get("/api/trading-summary/current")

    assert response.status_code == 404
    assert "No trading summary data available" in response.json()["detail"]


def test_get_trading_summary_paginated(monkeypatch) -> None:
    rows = _sample_trading_rows()
    monkeypatch.setattr(trading_summary, "fetch_latest_two_records", lambda: rows[:2])

    from app.schemas.trading_summary import TradingDayPoint, TradingPaginationInfo

    mock_history = [
        TradingDayPoint(
            date=r["date"],
            volume=r["volume"],
            value_idr=r["value_idr"],
            frequency=r["frequency"],
        )
        for r in reversed(rows)
    ]
    mock_pagination = TradingPaginationInfo(
        limit=30,
        has_more=False,
        oldest_date=mock_history[0].date,
        newest_date=mock_history[-1].date,
    )

    monkeypatch.setattr(
        trading_summary,
        "fetch_trading_history_paginated",
        lambda limit, before_date: (mock_history, mock_pagination),
    )

    response = TestClient(app).get("/api/trading-summary?limit=30")

    assert response.status_code == 200
    data = response.json()
    assert data["current"]["date"] == "2026-08-28"
    assert data["current"]["change"]["volume_pct"] == 15.53
    assert len(data["history"]) == 3
    # Chronological ascending
    assert data["history"][0]["date"] == "2026-08-26"
    assert data["history"][-1]["date"] == "2026-08-28"
    assert data["pagination"]["limit"] == 30
    assert data["pagination"]["has_more"] is False
    assert data["pagination"]["oldest_date"] == "2026-08-26"
    assert data["pagination"]["newest_date"] == "2026-08-28"


def test_compute_daily_change_calculation() -> None:
    today = {"volume": 110, "value_idr": 2200.0, "frequency": 22}
    yesterday = {"volume": 100, "value_idr": 2000.0, "frequency": 20}

    change = compute_daily_change(today, yesterday)
    assert change.volume_pct == 10.0
    assert change.value_pct == 10.0
    assert change.frequency_pct == 10.0

    no_prev_change = compute_daily_change(today, None)
    assert no_prev_change.volume_pct is None


def test_fetch_trading_history_paginated_logic(monkeypatch) -> None:
    from app.services import trading_summary as ts_service
    from app.services import trading_summary_repository as ts_repository

    rows = [
        {
            "date": f"2026-08-{i:02d}",
            "volume": 1000,
            "value_idr": 5000.0,
            "frequency": 50,
        }
        for i in range(25, 0, -1)
    ]  # 25 rows descending (25 down to 01)

    class MockQuery:
        def __init__(self, data):
            self.data = data
            self.cursor = None

        def select(self, *args):
            return self

        def lt(self, col, val):
            self.cursor = val
            return self

        def order(self, col, desc=True):
            return self

        def limit(self, count):
            self.count = count
            return self

        def execute(self):
            filtered = [
                r for r in self.data if not self.cursor or r["date"] < self.cursor
            ]
            return SimpleNamespace(data=filtered[: self.count])

    class MockSupabase:
        def table(self, name):
            assert name == "daily_trading_summary"
            return MockQuery(rows)

    monkeypatch.setattr(ts_repository, "get_supabase", lambda: MockSupabase())

    # Request limit=10: should get 10 items, has_more=True
    points, pagination = ts_service.fetch_trading_history_paginated(limit=10)
    assert len(points) == 10
    assert pagination.has_more is True
    assert pagination.oldest_date.isoformat() == "2026-08-16"
    assert pagination.newest_date.isoformat() == "2026-08-25"

    # Paginate backwards before 2026-08-16: should get 10 items (15 down to 06), has_more=True
    points_prev, pag_prev = ts_service.fetch_trading_history_paginated(
        limit=10, before_date="2026-08-16"
    )
    assert len(points_prev) == 10
    assert pag_prev.has_more is True
    assert points_prev[0].date.isoformat() == "2026-08-06"
    assert points_prev[-1].date.isoformat() == "2026-08-15"

    # Paginate backwards before 2026-08-06: remaining 5 items (05 down to 01), has_more=False
    points_end, pag_end = ts_service.fetch_trading_history_paginated(
        limit=10, before_date="2026-08-06"
    )
    assert len(points_end) == 5
    assert pag_end.has_more is False
    assert points_end[0].date.isoformat() == "2026-08-01"
    assert points_end[-1].date.isoformat() == "2026-08-05"
