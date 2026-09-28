"""Read daily market totals from IDX stock summaries."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from curl_cffi import requests

from app.config import get_settings

STOCK_SUMMARY_URL = "https://idx.co.id/primary/TradingSummary/GetStockSummary"
STOCK_SUMMARY_PAGE = (
    "https://idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/"
)


class IdxUnavailableError(Exception):
    """IDX could not supply a usable response."""


class IdxNoDataError(Exception):
    """IDX responded successfully but has no rows for the requested date."""


def _number(row: dict[str, Any], field: str) -> Decimal:
    raw = row.get(field)
    if raw is None or isinstance(raw, bool):
        raise IdxUnavailableError(f"IDX row has no valid {field}")
    try:
        value = Decimal(str(raw).replace(",", ""))
    except InvalidOperation as exc:
        raise IdxUnavailableError(f"IDX row has no valid {field}") from exc
    if not value.is_finite() or value < 0:
        raise IdxUnavailableError(f"IDX row has no valid {field}")
    return value


def _row_date(row: dict[str, Any]) -> date:
    raw = row.get("Date")
    if not isinstance(raw, str):
        raise IdxUnavailableError("IDX row has no valid Date")
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise IdxUnavailableError("IDX row has no valid Date") from exc


def summarize_stock_rows(payload: dict[str, Any], target_date: date) -> dict[str, Any]:
    """Validate a complete IDX page and sum its market-wide stock metrics."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise IdxUnavailableError("Unexpected IDX stock summary shape")
    if not rows:
        raise IdxNoDataError("IDX has no stock summary for this date")
    if payload.get("recordsTotal") is not None:
        try:
            total = int(payload["recordsTotal"])
        except (TypeError, ValueError) as exc:
            raise IdxUnavailableError("Invalid IDX row count") from exc
        if total > len(rows):
            raise IdxUnavailableError("IDX stock summary was truncated")

    volume = Decimal(0)
    value_idr = Decimal(0)
    frequency = Decimal(0)
    for row in rows:
        if not isinstance(row, dict):
            raise IdxUnavailableError("Invalid IDX stock row")
        if _row_date(row) != target_date:
            raise IdxNoDataError("IDX returned another trading date")
        volume += _number(row, "Volume")
        value_idr += _number(row, "Value")
        frequency += _number(row, "Frequency")

    if volume <= 0 or value_idr <= 0 or frequency <= 0:
        raise IdxUnavailableError("IDX stock summary totals are not positive")
    if volume != volume.to_integral_value() or frequency != frequency.to_integral_value():
        raise IdxUnavailableError("IDX volume or frequency is not integral")
    return {
        "date": target_date.isoformat(),
        "volume": int(volume),
        "value_idr": str(value_idr),
        "frequency": int(frequency),
    }


def fetch_idx_stock_summary(target_date: date) -> dict[str, Any]:
    """Fetch one date, matching the notebook's IDX request parameters."""
    headers = {
        "Referer": STOCK_SUMMARY_PAGE,
        "Accept": "application/json, text/plain, */*",
    }
    try:
        with requests.Session(impersonate="safari") as session:
            clearance = get_settings().idx_cf_clearance
            if clearance:
                session.cookies.set("cf_clearance", clearance, domain=".idx.co.id")
            # The notebook primes the session on the public page before its
            # data call. Failure here is harmless; the API response decides.
            try:
                session.get(STOCK_SUMMARY_PAGE, timeout=10)
            except Exception:
                pass
            response = session.get(
                STOCK_SUMMARY_URL,
                params={"length": 9999, "start": 0, "date": target_date.strftime("%Y%m%d")},
                headers=headers,
                timeout=30,
            )
            if response.status_code == 403 or "Just a moment" in response.text[:300]:
                raise IdxUnavailableError("IDX blocked the stock summary request")
            response.raise_for_status()
            return summarize_stock_rows(response.json(), target_date)
    except (IdxUnavailableError, IdxNoDataError):
        raise
    except Exception as exc:
        raise IdxUnavailableError("IDX stock summary request failed") from exc
