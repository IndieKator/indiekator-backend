from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.services import trading_summary_sync as sync
from app.services import idx_scraper
from app.services.idx_scraper import IdxNoDataError, IdxUnavailableError, summarize_stock_rows


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 25, hour, minute, tzinfo=sync.WIB)


def test_stock_summary_sums_only_valid_market_rows() -> None:
    payload = {
        "recordsTotal": 2,
        "data": [
            {"Date": "2026-09-25T00:00:00", "Volume": "1,200", "Value": "3000.50", "Frequency": 7},
            {"Date": "2026-09-25T00:00:00", "Volume": 300, "Value": "900.25", "Frequency": 2},
        ],
    }
    assert summarize_stock_rows(payload, date(2026, 9, 25)) == {
        "date": "2026-09-25", "volume": 1500, "value_idr": "3900.75", "frequency": 9,
    }


def test_stock_summary_rejects_incomplete_or_wrong_date() -> None:
    row = {"Date": "2026-09-24", "Volume": 10, "Value": 20, "Frequency": 2}
    with pytest.raises(IdxNoDataError):
        summarize_stock_rows({"data": [row]}, date(2026, 9, 25))
    row["Date"] = "2026-09-25"
    del row["Volume"]
    with pytest.raises(IdxUnavailableError):
        summarize_stock_rows({"data": [row]}, date(2026, 9, 25))
    with pytest.raises(IdxUnavailableError):
        summarize_stock_rows({"data": [row], "recordsTotal": 2}, date(2026, 9, 25))


def test_after_close_refresh_overrides_intraday_cooldown(monkeypatch) -> None:
    calls = []
    state = {"last_attempt_at": _at(16, 10).isoformat(), "finalized_at": None}
    latest = {"date": "2026-09-25", "updated_at": _at(16, 10).isoformat()}
    monkeypatch.setattr(sync, "fetch_latest_trading_summary", lambda: latest)
    monkeypatch.setattr(sync, "fetch_sync_state", lambda _date: state)
    monkeypatch.setattr(sync, "save_sync_state", lambda *args, **kwargs: calls.append(("state", kwargs)))
    monkeypatch.setattr(sync, "fetch_idx_stock_summary", lambda _date: {"date": "2026-09-25", "volume": 1, "value_idr": "2", "frequency": 3})
    monkeypatch.setattr(sync, "upsert_trading_records", lambda rows: calls.append(("upsert", rows)))

    assert sync.sync_trading_summary_on_demand(_at(19)) is False
    assert [call[0] for call in calls] == ["state", "upsert", "state"]
    assert calls[-1][1]["finalized_at"] == _at(19)


def test_finalized_weekend_reads_db_without_idx(monkeypatch) -> None:
    monkeypatch.setattr(sync, "fetch_latest_trading_summary", lambda: {"date": "2026-09-25"})
    monkeypatch.setattr(sync, "fetch_sync_state", lambda _date: {"finalized_at": _at(19).isoformat()})
    monkeypatch.setattr(sync, "fetch_idx_stock_summary", lambda _date: pytest.fail("IDX must not be called"))
    assert sync.sync_trading_summary_on_demand(datetime(2026, 9, 27, 12, tzinfo=sync.WIB)) is False


def test_open_market_respects_cooldown_and_retries_after_failure(monkeypatch) -> None:
    latest = {"date": "2026-09-25", "updated_at": _at(13).isoformat()}
    state = {"last_attempt_at": _at(13).isoformat(), "finalized_at": None}
    calls = []
    monkeypatch.setattr(sync, "fetch_latest_trading_summary", lambda: latest)
    monkeypatch.setattr(sync, "fetch_sync_state", lambda _date: state)
    monkeypatch.setattr(sync, "save_sync_state", lambda *args, **kwargs: calls.append("attempt"))
    monkeypatch.setattr(sync, "fetch_idx_stock_summary", lambda _date: (_ for _ in ()).throw(IdxUnavailableError()))
    assert sync.sync_trading_summary_on_demand(_at(13, 10)) is False
    assert sync.sync_trading_summary_on_demand(_at(13, 16)) is True
    assert calls == ["attempt"]


def test_failed_attempt_remains_stale_during_cooldown(monkeypatch) -> None:
    monkeypatch.setattr(
        sync,
        "fetch_latest_trading_summary",
        lambda: {"date": "2026-09-25", "updated_at": _at(13).isoformat()},
    )
    monkeypatch.setattr(
        sync,
        "fetch_sync_state",
        lambda _date: {"last_attempt_at": _at(13, 16).isoformat(), "finalized_at": None},
    )
    monkeypatch.setattr(sync, "fetch_idx_stock_summary", lambda _date: pytest.fail("IDX must not be called"))
    assert sync.sync_trading_summary_on_demand(_at(13, 20)) is True


def test_no_db_and_idx_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(sync, "fetch_latest_trading_summary", lambda: None)
    monkeypatch.setattr(sync, "fetch_sync_state", lambda _date: None)
    monkeypatch.setattr(sync, "save_sync_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync, "fetch_idx_stock_summary", lambda _date: (_ for _ in ()).throw(IdxUnavailableError()))
    with pytest.raises(sync.TradingSummaryUnavailableError):
        sync.sync_trading_summary_on_demand(_at(13))


def test_empty_final_fetch_keeps_previous_data_and_retries_later(monkeypatch) -> None:
    latest = {"date": "2026-09-25", "updated_at": _at(15).isoformat()}
    state = {"last_attempt_at": _at(15).isoformat(), "finalized_at": None}
    monkeypatch.setattr(sync, "fetch_latest_trading_summary", lambda: latest)
    monkeypatch.setattr(sync, "fetch_sync_state", lambda _date: state)
    monkeypatch.setattr(sync, "save_sync_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync, "fetch_idx_stock_summary", lambda _date: (_ for _ in ()).throw(IdxNoDataError()))
    assert sync.sync_trading_summary_on_demand(_at(19)) is True
    assert state["finalized_at"] is None


def test_cloudflare_403_is_not_treated_as_no_data(monkeypatch) -> None:
    class FakeSession:
        cookies = SimpleNamespace(set=lambda *args, **kwargs: None)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, url, **kwargs):
            if url == idx_scraper.STOCK_SUMMARY_PAGE:
                return SimpleNamespace(status_code=200)
            return SimpleNamespace(status_code=403, text="Just a moment")

    monkeypatch.setattr(idx_scraper.requests, "Session", lambda **kwargs: FakeSession())
    monkeypatch.setattr(idx_scraper, "get_settings", lambda: SimpleNamespace(idx_cf_clearance=""))
    with pytest.raises(IdxUnavailableError):
        idx_scraper.fetch_idx_stock_summary(date(2026, 9, 25))
