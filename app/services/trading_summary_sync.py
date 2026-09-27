"""Decide when an API read needs a fresh IDX trading summary."""

from datetime import date, datetime, time, timedelta, timezone
from threading import Lock
from zoneinfo import ZoneInfo

from app.services.idx_scraper import (
    IdxNoDataError,
    IdxUnavailableError,
    fetch_idx_stock_summary,
)
from app.services.trading_summary_repository import (
    fetch_latest_trading_summary,
    fetch_sync_state,
    save_sync_state,
    upsert_trading_records,
)

WIB = ZoneInfo("Asia/Jakarta")
MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(16, 15)
REFRESH_INTERVAL = timedelta(minutes=15)
_sync_lock = Lock()


class TradingSummaryUnavailableError(Exception):
    """No stored summary exists and IDX could not be reached."""


class TradingSummaryNotFoundError(Exception):
    """No stored summary or IDX rows exist for the relevant trading date."""


def _as_datetime(value: str | datetime) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def is_idx_market_open(now_wib: datetime) -> bool:
    return now_wib.weekday() < 5 and MARKET_OPEN <= now_wib.time() < MARKET_CLOSE


def _target_date(now_wib: datetime) -> date:
    target = now_wib.date()
    if target.weekday() < 5 and now_wib.time() >= MARKET_OPEN:
        return target
    target -= timedelta(days=1)
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    return target


def _after_close(target_date: date, now_wib: datetime) -> bool:
    return now_wib.date() > target_date or (
        now_wib.date() == target_date and now_wib.time() >= MARKET_CLOSE
    )


def _fetch_due(
    target_date: date,
    now_wib: datetime,
    state: dict | None,
    existing: dict | None,
) -> bool:
    if state and state.get("finalized_at"):
        return False
    if state and state.get("last_attempt_at"):
        last_attempt = _as_datetime(state["last_attempt_at"]).astimezone(WIB)
        # The first request after close must replace an intraday snapshot.
        crossed_close = _after_close(target_date, now_wib) and (
            last_attempt.date() == target_date and last_attempt.time() < MARKET_CLOSE
        )
        if not crossed_close and now_wib - last_attempt < REFRESH_INTERVAL:
            return False
    elif existing and existing.get("updated_at") and is_idx_market_open(now_wib):
        last_fetch = _as_datetime(existing["updated_at"]).astimezone(WIB)
        if now_wib - last_fetch < REFRESH_INTERVAL:
            return False
    return True


def sync_trading_summary_on_demand(now: datetime | None = None) -> bool:
    """Refresh when due; return whether the available DB data is stale."""
    instant = now or datetime.now(timezone.utc)
    now_wib = instant.astimezone(WIB)
    target = _target_date(now_wib)
    with _sync_lock:
        latest = fetch_latest_trading_summary()
        existing = latest if latest and str(latest["date"]) == target.isoformat() else None
        state = fetch_sync_state(target)
        if not _fetch_due(target, now_wib, state, existing):
            if latest:
                attempted_at = state.get("last_attempt_at") if state else None
                return bool(
                    attempted_at
                    and not state.get("finalized_at")
                    and _as_datetime(attempted_at) > _as_datetime(latest["updated_at"])
                )
            raise TradingSummaryNotFoundError

        save_sync_state(target, instant)
        try:
            record = fetch_idx_stock_summary(target)
        except IdxNoDataError as exc:
            if latest:
                return True
            raise TradingSummaryNotFoundError from exc
        except IdxUnavailableError as exc:
            if latest:
                return True
            raise TradingSummaryUnavailableError from exc

        record["updated_at"] = instant.isoformat()
        upsert_trading_records([record])
        save_sync_state(
            target,
            instant,
            finalized_at=instant if _after_close(target, now_wib) else None,
        )
        return False
