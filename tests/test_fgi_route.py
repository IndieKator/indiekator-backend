from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import fgi
from app.main import app


class FakeQuery:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.order_column: str | None = None
        self.reverse = False
        self.row_limit: int | None = None
        self.start_date: str | None = None

    def select(self, *_: str) -> "FakeQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.order_column = column
        self.reverse = desc
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.row_limit = value
        return self

    def gte(self, _column: str, value: str) -> "FakeQuery":
        self.start_date = value
        return self

    def execute(self) -> SimpleNamespace:
        rows = list(self.rows)
        if self.start_date:
            rows = [row for row in rows if row["week_date"] >= self.start_date]
        if self.order_column:
            rows.sort(key=lambda row: row[self.order_column], reverse=self.reverse)
        if self.row_limit is not None:
            rows = rows[: self.row_limit]
        return SimpleNamespace(data=rows)


class FakeSupabase:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def table(self, name: str) -> FakeQuery:
        assert name == "fgi_snapshots"
        return FakeQuery(self.rows)


def test_get_fgi_returns_current_and_ordered_six_month_history(monkeypatch) -> None:
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "week_date": "2026-08-30",
            "fgi": 61.2,
            "sentiment": "Greed",
            "close_price": 7200.0,
            "ma_125": 7000.0,
            "distance_pct": 2.86,
            "search_score": 60.0,
            "updated_at": now,
        },
        {
            "week_date": "2026-09-06",
            "fgi": 68.4,
            "sentiment": "Greed",
            "close_price": 7300.0,
            "ma_125": 7050.0,
            "distance_pct": 3.55,
            "search_score": 65.0,
            "updated_at": now,
        },
    ]
    monkeypatch.setattr(fgi, "get_supabase", lambda: FakeSupabase(rows))
    monkeypatch.setattr(fgi, "run_ingestion", lambda: (_ for _ in ()).throw(AssertionError()))

    response = TestClient(app).get("/api/fgi")

    assert response.status_code == 200
    assert response.json()["current"] == {
        "date": "2026-09-06",
        "value": 68.4,
        "sentiment": "Greed",
        "close_price": 7300.0,
        "ma_125": 7050.0,
        "ema_13": None,
        "distance_pct": 3.55,
        "search_score": 65.0,
        "trends_mean": None,
        "trend_ihsg": None,
        "trend_idx_composite": None,
        "trend_indeks_harga_saham_gabungan": None,
    }
    assert [point["date"] for point in response.json()["history"]] == [
        "2026-08-30",
        "2026-09-06",
    ]
    assert response.json()["is_stale"] is False


def test_get_fgi_returns_stale_snapshot_when_refresh_fails(monkeypatch) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    rows = [
        {
            "week_date": "2026-09-06",
            "fgi": 41.0,
            "sentiment": "Fear",
            "close_price": 6900.0,
            "ma_125": 7100.0,
            "distance_pct": -2.82,
            "search_score": 38.0,
            "updated_at": stale,
        },
    ]
    monkeypatch.setattr(fgi, "get_supabase", lambda: FakeSupabase(rows))
    monkeypatch.setattr(fgi, "run_ingestion", lambda: (_ for _ in ()).throw(RuntimeError()))

    response = TestClient(app).get("/api/fgi")

    assert response.status_code == 200
    assert response.json()["is_stale"] is True


def test_get_fgi_refreshes_through_the_consolidated_ingestion(monkeypatch) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    rows = [
        {
            "week_date": "2026-09-06",
            "fgi": 41.0,
            "sentiment": "Fear",
            "close_price": 6900.0,
            "ma_125": 7100.0,
            "distance_pct": -2.82,
            "search_score": 38.0,
            "updated_at": stale,
        },
    ]
    refresh_calls = 0

    def refresh() -> dict:
        nonlocal refresh_calls
        refresh_calls += 1
        rows[0]["updated_at"] = datetime.now(timezone.utc).isoformat()
        return {"status": "success", "rows_upserted": 1, "message": "refreshed"}

    monkeypatch.setattr(fgi, "get_supabase", lambda: FakeSupabase(rows))
    monkeypatch.setattr(fgi, "run_ingestion", refresh)

    response = TestClient(app).get("/api/fgi")

    assert response.status_code == 200
    assert response.json()["is_stale"] is False
    assert refresh_calls == 1


def test_get_fgi_returns_503_when_refresh_fails_without_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(fgi, "get_supabase", lambda: FakeSupabase([]))
    monkeypatch.setattr(fgi, "run_ingestion", lambda: (_ for _ in ()).throw(RuntimeError()))

    response = TestClient(app).get("/api/fgi")

    assert response.status_code == 503
