from types import SimpleNamespace

import pytest

from app.services import ingestion


class FakeTable:
    def __init__(self, name: str, calls: list[tuple], rows: list[dict]):
        self.name = name
        self.calls = calls
        self.rows = rows

    def select(self, *_: str) -> "FakeTable":
        return self

    def order(self, *_: str, **__: object) -> "FakeTable":
        return self

    def eq(self, *_: object) -> "FakeTable":
        return self

    def neq(self, *_: object) -> "FakeTable":
        return self

    def insert(self, payload: object) -> "FakeTable":
        self.calls.append(("insert", self.name, payload))
        return self

    def update(self, payload: object) -> "FakeTable":
        self.calls.append(("update", self.name, payload))
        return self

    def delete(self) -> "FakeTable":
        self.calls.append(("delete", self.name, None))
        return self

    def execute(self) -> SimpleNamespace:
        if self.name == "ingestion_runs":
            return SimpleNamespace(data=[{"id": "run-1"}])
        return SimpleNamespace(data=self.rows)


class FakeSupabase:
    def __init__(self, snapshots: list[dict] | None = None):
        self.calls: list[tuple] = []
        self.tables_touched: list[str] = []
        self.snapshots = snapshots or []

    def table(self, name: str) -> FakeTable:
        self.tables_touched.append(name)
        rows = self.snapshots if name == "fgi_snapshots" else []
        return FakeTable(name, self.calls, rows)

    def payloads(self, operation: str, table: str) -> list[object]:
        return [p for op, t, p in self.calls if op == operation and t == table]


SNAPSHOTS = [
    {"week_date": "2026-08-02", "sentiment": "Fear", "close_price": 7000.0},
    {"week_date": "2026-08-09", "sentiment": "Fear", "close_price": 6900.0},
    {"week_date": "2026-08-16", "sentiment": "Neutral", "close_price": 7100.0},
]


@pytest.fixture
def fake(monkeypatch) -> FakeSupabase:
    supabase = FakeSupabase(SNAPSHOTS)
    monkeypatch.setattr(ingestion, "get_supabase", lambda: supabase)
    return supabase


def test_run_ingestion_never_touches_the_dropped_daily_sentiment_table(
    fake, monkeypatch
) -> None:
    monkeypatch.setattr(ingestion, "run_fgi_ingestion", lambda: 3)

    ingestion.run_ingestion()

    assert "daily_sentiment" not in fake.tables_touched


def test_run_ingestion_writes_only_the_snapshot_zone_and_run_tables(
    fake, monkeypatch
) -> None:
    monkeypatch.setattr(ingestion, "run_fgi_ingestion", lambda: 3)

    ingestion.run_ingestion()

    assert set(fake.tables_touched) == {
        "ingestion_runs",
        "fgi_snapshots",
        "zone_periods",
    }


def test_run_ingestion_marks_the_run_successful_with_the_upserted_count(
    fake, monkeypatch
) -> None:
    monkeypatch.setattr(ingestion, "run_fgi_ingestion", lambda: 3)

    result = ingestion.run_ingestion()

    assert result["status"] == "success"
    assert result["rows_upserted"] == 3

    update = fake.payloads("update", "ingestion_runs")[0]
    assert update["status"] == "success"
    assert update["rows_upserted"] == 3
    assert update["finished_at"]


def test_run_ingestion_opens_the_run_row_before_doing_work(fake, monkeypatch) -> None:
    monkeypatch.setattr(ingestion, "run_fgi_ingestion", lambda: 3)

    ingestion.run_ingestion()

    assert fake.payloads("insert", "ingestion_runs")[0] == {"status": "running"}


def test_run_ingestion_rebuilds_zone_periods_from_the_snapshots(
    fake, monkeypatch
) -> None:
    monkeypatch.setattr(ingestion, "run_fgi_ingestion", lambda: 3)

    ingestion.run_ingestion()

    assert ("delete", "zone_periods", None) in fake.calls
    inserted = fake.payloads("insert", "zone_periods")[0]
    assert [row["zone"] for row in inserted] == ["fear", "neutral"]


def test_run_ingestion_deletes_zone_periods_only_after_deriving_replacements(
    fake, monkeypatch
) -> None:
    monkeypatch.setattr(ingestion, "run_fgi_ingestion", lambda: 3)

    ingestion.run_ingestion()

    zone_ops = [op for op, table, _ in fake.calls if table == "zone_periods"]
    assert zone_ops == ["delete", "insert"]


def test_run_ingestion_leaves_zone_periods_untouched_when_no_snapshots_exist(
    monkeypatch,
) -> None:
    supabase = FakeSupabase([])
    monkeypatch.setattr(ingestion, "get_supabase", lambda: supabase)
    monkeypatch.setattr(ingestion, "run_fgi_ingestion", lambda: 0)

    ingestion.run_ingestion()

    assert [op for op, table, _ in supabase.calls if table == "zone_periods"] == []


def test_run_ingestion_marks_the_run_failed_and_reraises(fake, monkeypatch) -> None:
    def boom() -> int:
        raise RuntimeError("sectors unavailable")

    monkeypatch.setattr(ingestion, "run_fgi_ingestion", boom)

    with pytest.raises(RuntimeError, match="sectors unavailable"):
        ingestion.run_ingestion()

    update = fake.payloads("update", "ingestion_runs")[0]
    assert update["status"] == "failed"
    assert update["error_message"] == "sectors unavailable"
    assert update["finished_at"]


def test_run_ingestion_does_not_write_zone_periods_when_the_pipeline_fails(
    fake, monkeypatch
) -> None:
    monkeypatch.setattr(
        ingestion,
        "run_fgi_ingestion",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError):
        ingestion.run_ingestion()

    assert [op for op, table, _ in fake.calls if table == "zone_periods"] == []
