from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import fgi
from app.main import app
from app.services.fgi_engine import PRICE_WEIGHT, SEARCH_WEIGHT, classify_fgi


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


def _snapshot(
    weeks_ago: int,
    price_score: float,
    search_score: float = 60.0,
    sentiment: str | None = None,
) -> dict:
    """Build an internally consistent snapshot row.

    ``distance_pct`` and ``fgi`` are derived from ``price_score`` using the same
    relationships the engine applies, so assertions about the breakdown
    reconstructing the index value are meaningful rather than tautological.
    """
    distance_pct = (price_score - 50) * 0.12
    fgi_value = round(PRICE_WEIGHT * price_score + SEARCH_WEIGHT * search_score, 2)
    return {
        "week_date": (date.today() - timedelta(weeks=weeks_ago)).isoformat(),
        "fgi": fgi_value,
        "sentiment": sentiment or classify_fgi(fgi_value),
        "close_price": 7300.0,
        "ma_30": 7050.0,
        "distance_pct": distance_pct,
        "price_score": price_score,
        "search_score": search_score,
        "trends_mean": 62.0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# fgi values: 48.0, 54.0, 60.0, 63.0, 66.0
FIVE_WEEKS = [
    _snapshot(4, 40.0),
    _snapshot(3, 50.0),
    _snapshot(2, 60.0),
    _snapshot(1, 65.0),
    _snapshot(0, 70.0),
]


def _client(monkeypatch, rows: list[dict]) -> TestClient:
    monkeypatch.setattr(fgi, "get_supabase", lambda: FakeSupabase(rows))
    monkeypatch.setattr(
        fgi,
        "run_ingestion",
        lambda: pytest.fail("fresh snapshots must not trigger a refresh"),
    )
    return TestClient(app)


def test_current_reports_zone_and_summary(monkeypatch) -> None:
    response = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/current")

    assert response.status_code == 200
    body = response.json()
    assert body["value"] == 66.0
    assert body["sentiment"] == "Greed"
    assert body["zone"] == "greed"
    assert body["zone_label"] == "Greed"
    assert "Greed" in body["summary"]
    assert body["is_stale"] is False


def test_current_reports_the_30_period_moving_average(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/current").json()

    assert body["ma_30"] == 7050.0
    assert "ma_125" not in body
    assert "MA 30" in body["summary"]
    assert "MA 125" not in body["summary"]


def test_breakdown_describes_price_momentum_against_ma_30(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/breakdown").json()
    price = next(c for c in body["components"] if c["name"] == "price_momentum")

    assert "MA 30" in price["description"]


def test_current_exposes_the_raw_component_scores(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/current").json()

    assert body["price_score"] == 70.0
    assert body["search_score"] == 60.0
    assert body["trends_mean"] == 62.0


def test_current_computes_week_over_week_deltas(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/current").json()

    assert body["delta"]["vs_last_week"] == pytest.approx(3.0)
    assert body["delta"]["vs_month_ago"] == pytest.approx(18.0)


def test_current_leaves_deltas_null_without_enough_history(monkeypatch) -> None:
    body = _client(monkeypatch, [_snapshot(0, 70.0)]).get("/api/fgi/current").json()

    assert body["delta"]["vs_last_week"] is None
    assert body["delta"]["vs_month_ago"] is None


def test_current_maps_each_sentiment_label_to_its_zone(monkeypatch) -> None:
    pairs = [
        ("Extreme Fear", "extreme_fear"),
        ("Fear", "fear"),
        ("Neutral", "neutral"),
        ("Greed", "greed"),
        ("Extreme Greed", "extreme_greed"),
    ]
    for label, expected_zone in pairs:
        client = _client(monkeypatch, [_snapshot(0, 50.0, sentiment=label)])
        assert client.get("/api/fgi/current").json()["zone"] == expected_zone


def test_current_rejects_an_unrecognised_sentiment_label(monkeypatch) -> None:
    rows = [_snapshot(0, 50.0, sentiment="Euphoria")]
    monkeypatch.setattr(fgi, "get_supabase", lambda: FakeSupabase(rows))

    with pytest.raises(ValueError, match="Euphoria"):
        TestClient(app).get("/api/fgi/current")


def test_current_returns_503_without_any_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(fgi, "get_supabase", lambda: FakeSupabase([]))
    monkeypatch.setattr(
        fgi, "run_ingestion", lambda: (_ for _ in ()).throw(RuntimeError())
    )

    assert TestClient(app).get("/api/fgi/current").status_code == 503


def test_history_returns_points_oldest_first(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/history").json()

    assert body["range"] == "1y"
    assert body["count"] == 5
    assert [point["date"] for point in body["data"]] == sorted(
        point["date"] for point in body["data"]
    )


def test_history_narrows_to_the_requested_range(monkeypatch) -> None:
    rows = [_snapshot(30, 40.0), _snapshot(0, 70.0)]

    body = _client(monkeypatch, rows).get("/api/fgi/history?range=3m").json()

    assert body["range"] == "3m"
    assert body["count"] == 1


def test_history_range_all_returns_every_snapshot(monkeypatch) -> None:
    rows = [_snapshot(200, 40.0), _snapshot(0, 70.0)]

    body = _client(monkeypatch, rows).get("/api/fgi/history?range=all").json()

    assert body["count"] == 2


def test_history_rejects_an_unsupported_range(monkeypatch) -> None:
    response = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/history?range=5y")

    assert response.status_code == 422


def test_breakdown_reports_exactly_two_labelled_components(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/breakdown").json()

    assert [component["label"] for component in body["components"]] == [
        "Price Momentum",
        "Public Sentiment",
    ]
    assert [component["name"] for component in body["components"]] == [
        "price_momentum",
        "public_sentiment",
    ]


def test_breakdown_uses_the_engine_weights(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/breakdown").json()
    weights = {c["name"]: c["weight"] for c in body["components"]}

    assert weights["price_momentum"] == PRICE_WEIGHT
    assert weights["public_sentiment"] == SEARCH_WEIGHT


def test_breakdown_contributions_reconstruct_the_index_value(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/breakdown").json()

    total = sum(component["contribution"] for component in body["components"])
    assert total == pytest.approx(body["value"], abs=0.02)


def test_breakdown_reports_the_raw_component_values(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi/breakdown").json()
    values = {c["name"]: c["value"] for c in body["components"]}

    assert values["price_momentum"] == 70.0
    assert values["public_sentiment"] == 60.0


def test_root_fgi_endpoint_returns_history_older_than_six_months(monkeypatch) -> None:
    """Regression: a fixed trailing window used to truncate the chart.

    The root endpoint previously filtered to roughly the last 183 days, which
    capped the dashboard's earliest plotted point regardless of the range the
    user selected.
    """
    oldest = _snapshot(50, 40.0)
    rows = [oldest, _snapshot(0, 70.0)]

    body = _client(monkeypatch, rows).get("/api/fgi").json()

    assert len(body["history"]) == 2
    assert body["history"][0]["date"] == oldest["week_date"]


def test_root_fgi_endpoint_returns_every_snapshot(monkeypatch) -> None:
    rows = [_snapshot(weeks, 50.0) for weeks in (200, 120, 60, 10, 0)]

    body = _client(monkeypatch, rows).get("/api/fgi").json()

    assert len(body["history"]) == len(rows)


def test_root_fgi_endpoint_still_serves_its_original_contract(monkeypatch) -> None:
    body = _client(monkeypatch, FIVE_WEEKS).get("/api/fgi").json()

    assert set(body) == {"current", "history", "updated_at", "is_stale"}
    assert set(body["current"]) == {
        "date",
        "value",
        "sentiment",
        "close_price",
        "ma_30",
        "ema_13",
        "distance_pct",
        "search_score",
        "trends_mean",
    }
