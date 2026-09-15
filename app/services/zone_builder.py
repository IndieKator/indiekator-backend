"""Derive Fear & Greed zone episodes from weekly FGI snapshots.

Replaces the V1 ``zone_analyzer`` module, which consumed daily
``daily_sentiment`` records. Episodes are now run-length encoded over weekly
``fgi_snapshots`` rows, so ``duration_days`` lands on multiples of seven and
boundaries fall on week-end dates.
"""

from datetime import date
from typing import Any

# Maps the stored fgi_snapshots.sentiment label onto the ZoneKey literal used by
# zone_periods.zone and the API schema.
#
# The stored label is read rather than recomputed from the numeric score.
# app/services/zones.score_to_zone uses closed bands (0-25, 26-45, 46-55, 56-75,
# 76-100), so a fractional score such as 25.5 matches no band and falls through
# to its trailing "extreme_greed" return. Reading the label the ingestion engine
# already classified avoids that defect entirely.
SENTIMENT_TO_ZONE: dict[str, str] = {
    "Extreme Fear": "extreme_fear",
    "Fear": "fear",
    "Neutral": "neutral",
    "Greed": "greed",
    "Extreme Greed": "extreme_greed",
}


def build_zone_periods(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse consecutive same-sentiment weeks into zone episodes.

    Each snapshot needs ``week_date``, ``sentiment``, and ``close_price``.
    Returns rows shaped for insertion into ``zone_periods``, ordered oldest
    first. The episode containing the newest ``week_date`` is left open with
    ``exit_date`` set to ``None``.

    An empty input yields an empty list, which callers treat as "leave the
    existing table alone" rather than "delete everything".
    """
    if not snapshots:
        return []

    ordered = sorted(snapshots, key=lambda row: _as_date(row["week_date"]))

    periods: list[dict[str, Any]] = []
    run_start = 0
    for index in range(1, len(ordered) + 1):
        still_same_run = index < len(ordered) and _zone_of(ordered[index]) == _zone_of(
            ordered[run_start]
        )
        if still_same_run:
            continue
        periods.append(
            _build_period(
                ordered,
                entry_index=run_start,
                exit_index=index - 1,
                is_open=index == len(ordered),
            )
        )
        run_start = index

    return periods


def _build_period(
    rows: list[dict[str, Any]],
    entry_index: int,
    exit_index: int,
    is_open: bool,
) -> dict[str, Any]:
    entry_row = rows[entry_index]
    exit_row = rows[exit_index]

    entry_date = _as_date(entry_row["week_date"])
    exit_date = _as_date(exit_row["week_date"])
    entry_price = float(entry_row["close_price"])
    exit_price = float(exit_row["close_price"])

    # Guard against a zero entry price rather than dividing by it.
    return_pct = (
        ((exit_price - entry_price) / entry_price) * 100 if entry_price else 0.0
    )

    return {
        "zone": _zone_of(entry_row),
        "entry_date": entry_date.isoformat(),
        "exit_date": None if is_open else exit_date.isoformat(),
        "duration_days": (exit_date - entry_date).days + 1,
        "return_pct": round(return_pct, 4),
    }


def _zone_of(row: dict[str, Any]) -> str:
    label = row["sentiment"]
    try:
        return SENTIMENT_TO_ZONE[label]
    except KeyError:
        raise ValueError(
            f"Unrecognised fgi_snapshots.sentiment label: {label!r}"
        ) from None


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
