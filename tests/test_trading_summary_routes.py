from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import trading_summary
from app.main import app


class FakeTradingQuery:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.order_column: str | None = None
        self.reverse = False
        self.row_limit: int | None = None
        self.start_date: str | None = None

    def select(self, *_: str) -> "FakeTradingQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeTradingQuery":
        self.order_column = column
        self.reverse = desc
        return self

    def limit(self, value: int) -> "FakeTradingQuery":
        self.row_limit = value
        return self

    def gte(self, _column: str, value: str) -> "FakeTradingQuery":
        self.start_date = value
        return self

    def execute(self) -> SimpleNamespace:
        rows = list(self.rows)
        if self.start_date:
            rows = [row for row in rows if str(row["date"]) >= self.start_date]
        if self.order_column:
            rows.sort(key=lambda row: str(row[self.order_column]), reverse=self.reverse)
        if self.row_limit is not None:
            rows = rows[: self.row_limit]
        return SimpleNamespace(data=rows)


class FakeSupabaseForTrading:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def table(self, name: str) -> FakeTradingQuery:
        assert name == "daily_trading_summary"
        return FakeTradingQuery(self.rows)


def _sample_trading_rows() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "date": "2026-08-27",
            "volume": 8_500_000_000,
            "value_idr": 11_200_000_000_000.0,
            "frequency": 1_150_000,
            "volume_ma_20": 8_000_000_000.0,
            "frequency_ma_20": 1_100_000.0,
            "value_ma_20": 10_500_000_000_000.0,
            "updated_at": now,
        },
        {
            "date": "2026-08-28",
            "volume": 9_820_000_000,
            "value_idr": 12_400_000_000_000.0,
            "frequency": 1_280_000,
            "volume_ma_20": 8_710_000_000.0,
            "frequency_ma_20": 1_150_000.0,
            "value_ma_20": 11_200_000_000_000.0,
            "updated_at": now,
        },
    ]


def test_get_current_trading_summary(monkeypatch) -> None:
    rows = _sample_trading_rows()
    monkeypatch.setattr(
        trading_summary, "fetch_latest_trading_summary", lambda: rows[1]
    )
    monkeypatch.setattr(
        trading_summary, "fetch_recent_trading_records", lambda limit: rows[::-1]
    )

    response = TestClient(app).get("/api/trading-summary/current")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-08-28"
    assert data["volume"] == 9_820_000_000
    assert data["value_idr"] == 12_400_000_000_000.0
    assert data["frequency"] == 1_280_000
    assert data["volume_ma_20"] == 8_710_000_000.0
    assert data["volume_vs_ma_20_pct"] == 12.74
    assert data["frequency_ma_20"] == 1_150_000.0
    assert data["frequency_vs_ma_20_pct"] == 11.30


def test_get_current_trading_summary_404_when_empty(monkeypatch) -> None:
    monkeypatch.setattr(trading_summary, "fetch_latest_trading_summary", lambda: None)

    response = TestClient(app).get("/api/trading-summary/current")

    assert response.status_code == 404
    assert "No trading summary data available" in response.json()["detail"]


def test_get_trading_summary_history(monkeypatch) -> None:
    rows = _sample_trading_rows()
    monkeypatch.setattr(
        trading_summary, "fetch_trading_summary_history", lambda start_date: rows
    )

    response = TestClient(app).get("/api/trading-summary/history?range=30d")

    assert response.status_code == 200
    data = response.json()
    assert data["range"] == "30d"
    assert data["count"] == 2
    assert len(data["data"]) == 2
    assert data["data"][0]["date"] == "2026-08-27"
    assert data["data"][1]["date"] == "2026-08-28"


def test_get_trading_summary_history_with_custom_days(monkeypatch) -> None:
    rows = _sample_trading_rows()
    monkeypatch.setattr(
        trading_summary, "fetch_trading_summary_history", lambda start_date: rows
    )

    response = TestClient(app).get("/api/trading-summary/history?days=14")

    assert response.status_code == 200
    data = response.json()
    assert data["range"] == "14d"
    assert data["count"] == 2


def test_get_trading_summary_composite(monkeypatch) -> None:
    rows = _sample_trading_rows()
    monkeypatch.setattr(
        trading_summary, "fetch_latest_trading_summary", lambda: rows[1]
    )
    monkeypatch.setattr(
        trading_summary, "fetch_recent_trading_records", lambda limit: rows[::-1]
    )
    monkeypatch.setattr(
        trading_summary, "fetch_trading_summary_history", lambda start_date=None: rows
    )

    response = TestClient(app).get("/api/trading-summary")

    assert response.status_code == 200
    data = response.json()
    assert data["current"]["date"] == "2026-08-28"
    assert data["current"]["volume"] == 9_820_000_000
    assert len(data["history"]) == 2


def test_compute_20d_metrics_dynamic() -> None:
    from app.services.trading_summary import compute_20d_metrics

    # Test dynamic computation when MA is not pre-calculated
    rows = [{"volume": 100, "frequency": 10, "value_idr": 1000} for _ in range(20)]
    latest = {"volume": 120, "frequency": 15, "value_idr": 1100}
    metrics = compute_20d_metrics(latest, rows)

    assert metrics["volume_ma_20"] == 100.0
    assert metrics["volume_vs_ma_20_pct"] == 20.0
    assert metrics["frequency_ma_20"] == 10.0
    assert metrics["frequency_vs_ma_20_pct"] == 50.0
    assert metrics["value_ma_20"] == 1000.0
    assert metrics["value_vs_ma_20_pct"] == 10.0
