"""Shape the Sectors ``/companies/top-changes/`` payload for the dashboard.

The upstream response is a nested object keyed by classification then period::

    {"top_gainers": {"7d": [ {name, symbol, price_change, ...} ]},
     "top_losers":  {"7d": [ ... ]}}

``price_change`` arrives as a ratio (``0.05`` == +5%). This module normalizes
ticker symbols (strips the ``.JK`` suffix), converts the ratio to a percentage,
and regroups the data by period so a client can render one gainers/losers pair
per lookback window.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from app.schemas.market_movers import MoversPeriod, MoversResponse, MoverStock
from app.services.sectors_client import fetch_top_movers

_CLASSIFICATIONS = ("top_gainers", "top_losers")


def _clean_symbol(symbol: str) -> str:
    return symbol.upper().replace(".JK", "")


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _to_stock(row: dict[str, Any]) -> MoverStock:
    ratio = float(row.get("price_change") or 0.0)
    return MoverStock(
        symbol=_clean_symbol(str(row.get("symbol", ""))),
        name=str(row.get("name", "")),
        last_close_price=float(row.get("last_close_price") or 0.0),
        price_change_ratio=ratio,
        price_change_pct=round(ratio * 100, 2),
        latest_close_date=_parse_date(row.get("latest_close_date")),
    )


def _stocks(section: Any) -> dict[str, list[MoverStock]]:
    """Map one classification's ``{period: [rows]}`` into typed lists by period."""
    result: dict[str, list[MoverStock]] = {}
    if not isinstance(section, dict):
        return result
    for period, rows in section.items():
        if isinstance(rows, list):
            result[period] = [_to_stock(r) for r in rows if isinstance(r, dict)]
    return result


def _ordered_periods(requested: Iterable[str], seen: Iterable[str]) -> list[str]:
    # Preserve the caller's requested order, then append any extra periods the
    # API returned that were not explicitly asked for.
    ordered = [p for p in requested if p in seen]
    ordered += [p for p in seen if p not in ordered]
    return ordered


def build_movers_response(
    payload: dict[str, Any], requested_periods: list[str]
) -> MoversResponse:
    gainers_by_period = _stocks(payload.get("top_gainers"))
    losers_by_period = _stocks(payload.get("top_losers"))

    all_periods = set(gainers_by_period) | set(losers_by_period)
    periods = [
        MoversPeriod(
            period=period,
            top_gainers=gainers_by_period.get(period, []),
            top_losers=losers_by_period.get(period, []),
        )
        for period in _ordered_periods(requested_periods, all_periods)
    ]

    return MoversResponse(periods=periods, updated_at=datetime.now(timezone.utc))


def get_top_movers(
    periods: str = "7d",
    n_stock: int = 5,
    min_mcap_billion: int = 5000,
) -> MoversResponse:
    """Fetch and shape top movers for the requested comma-separated periods."""
    payload = fetch_top_movers(
        classifications="top_gainers,top_losers",
        periods=periods,
        n_stock=n_stock,
        min_mcap_billion=min_mcap_billion,
    )
    requested = [p.strip() for p in periods.split(",") if p.strip()]
    return build_movers_response(payload, requested)
