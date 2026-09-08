from datetime import date
from typing import Any

import pandas as pd


def detect_zone_periods(records: list[dict]) -> list[dict[str, Any]]:
    if not records:
        return []

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    periods: list[dict[str, Any]] = []
    current_zone: str | None = None
    entry_idx: int | None = None

    for i, row in df.iterrows():
        zone = row["zone"]
        if zone != current_zone:
            if current_zone is not None and entry_idx is not None:
                periods.append(_build_period(df, entry_idx, i - 1, current_zone))
            current_zone = zone
            entry_idx = i

    if current_zone is not None and entry_idx is not None:
        periods.append(
            _build_period(df, entry_idx, len(df) - 1, current_zone, is_last=True)
        )

    return periods


def _build_period(
    df: pd.DataFrame,
    entry_idx: int,
    exit_idx: int,
    zone: str,
    is_last: bool = False,
) -> dict[str, Any]:
    entry_row = df.iloc[entry_idx]
    exit_row = df.iloc[exit_idx]
    entry_date: date = entry_row["date"].date()
    exit_date: date = exit_row["date"].date()
    entry_price = float(entry_row["close_price"])
    exit_price = float(exit_row["close_price"])
    duration = (exit_date - entry_date).days + 1
    return_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price else 0

    return {
        "zone": zone,
        "entry_date": entry_date.isoformat(),
        "exit_date": None if is_last else exit_date.isoformat(),
        "duration_days": duration,
        "return_pct": round(return_pct, 4),
    }
