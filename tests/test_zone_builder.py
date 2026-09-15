from datetime import date

import pytest

from app.services.zone_builder import SENTIMENT_TO_ZONE, build_zone_periods


def _snapshot(week_date: str, sentiment: str, close_price: float) -> dict:
    return {
        "week_date": week_date,
        "sentiment": sentiment,
        "close_price": close_price,
    }


def test_build_zone_periods_returns_empty_for_no_snapshots() -> None:
    assert build_zone_periods([]) == []


def test_build_zone_periods_collapses_consecutive_same_sentiment_weeks() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Fear", 7000.0),
        _snapshot("2026-08-09", "Fear", 6900.0),
        _snapshot("2026-08-16", "Neutral", 7100.0),
    ]

    periods = build_zone_periods(snapshots)

    assert [p["zone"] for p in periods] == ["fear", "neutral"]
    assert periods[0]["entry_date"] == "2026-08-02"
    assert periods[0]["exit_date"] == "2026-08-09"
    assert periods[1]["entry_date"] == "2026-08-16"


def test_build_zone_periods_leaves_only_the_newest_episode_open() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Fear", 7000.0),
        _snapshot("2026-08-09", "Greed", 7200.0),
        _snapshot("2026-08-16", "Greed", 7300.0),
    ]

    periods = build_zone_periods(snapshots)

    open_periods = [p for p in periods if p["exit_date"] is None]
    assert len(open_periods) == 1
    assert open_periods[0] is periods[-1]
    assert open_periods[0]["entry_date"] == "2026-08-09"


def test_build_zone_periods_sorts_unordered_input_by_week_date() -> None:
    snapshots = [
        _snapshot("2026-08-16", "Neutral", 7100.0),
        _snapshot("2026-08-02", "Fear", 7000.0),
        _snapshot("2026-08-09", "Fear", 6900.0),
    ]

    periods = build_zone_periods(snapshots)

    assert [p["entry_date"] for p in periods] == ["2026-08-02", "2026-08-16"]


def test_build_zone_periods_maps_every_sentiment_label_to_its_zone_key() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Extreme Fear", 6000.0),
        _snapshot("2026-08-09", "Fear", 6100.0),
        _snapshot("2026-08-16", "Neutral", 6200.0),
        _snapshot("2026-08-23", "Greed", 6300.0),
        _snapshot("2026-08-30", "Extreme Greed", 6400.0),
    ]

    periods = build_zone_periods(snapshots)

    assert [p["zone"] for p in periods] == [
        "extreme_fear",
        "fear",
        "neutral",
        "greed",
        "extreme_greed",
    ]
    assert set(SENTIMENT_TO_ZONE.values()) == {p["zone"] for p in periods}


def test_build_zone_periods_computes_inclusive_duration_in_days() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Fear", 7000.0),
        _snapshot("2026-08-16", "Fear", 6900.0),
    ]

    periods = build_zone_periods(snapshots)

    assert periods[0]["duration_days"] == 15


def test_build_zone_periods_computes_return_pct_across_the_episode() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Fear", 1000.0),
        _snapshot("2026-08-09", "Fear", 1100.0),
        _snapshot("2026-08-16", "Neutral", 1200.0),
    ]

    periods = build_zone_periods(snapshots)

    assert periods[0]["return_pct"] == pytest.approx(10.0)


def test_build_zone_periods_return_pct_sign_follows_price_direction() -> None:
    falling = build_zone_periods(
        [
            _snapshot("2026-08-02", "Fear", 1000.0),
            _snapshot("2026-08-09", "Fear", 900.0),
            _snapshot("2026-08-16", "Neutral", 950.0),
        ]
    )

    assert falling[0]["return_pct"] < 0


def test_build_zone_periods_returns_zero_return_for_zero_entry_price() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Fear", 0.0),
        _snapshot("2026-08-09", "Fear", 900.0),
        _snapshot("2026-08-16", "Neutral", 950.0),
    ]

    periods = build_zone_periods(snapshots)

    assert periods[0]["return_pct"] == 0.0


def test_build_zone_periods_partitions_input_without_gap_or_overlap() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Fear", 7000.0),
        _snapshot("2026-08-09", "Fear", 6900.0),
        _snapshot("2026-08-16", "Neutral", 7100.0),
        _snapshot("2026-08-23", "Greed", 7300.0),
        _snapshot("2026-08-30", "Fear", 7000.0),
    ]

    periods = build_zone_periods(snapshots)

    entries = [date.fromisoformat(p["entry_date"]) for p in periods]
    assert entries == sorted(entries)
    assert entries[0] == date(2026, 8, 2)
    # Each closed episode must hand off to the next entry with no overlap.
    for earlier, later in zip(periods, periods[1:]):
        assert date.fromisoformat(earlier["exit_date"]) < date.fromisoformat(
            later["entry_date"]
        )


def test_build_zone_periods_accepts_date_objects_for_week_date() -> None:
    snapshots = [
        {"week_date": date(2026, 8, 2), "sentiment": "Fear", "close_price": 7000.0},
        {"week_date": date(2026, 8, 9), "sentiment": "Neutral", "close_price": 7100.0},
    ]

    periods = build_zone_periods(snapshots)

    assert periods[0]["entry_date"] == "2026-08-02"


def test_build_zone_periods_is_idempotent_for_unchanged_input() -> None:
    snapshots = [
        _snapshot("2026-08-02", "Fear", 7000.0),
        _snapshot("2026-08-09", "Neutral", 7100.0),
    ]

    assert build_zone_periods(snapshots) == build_zone_periods(snapshots)


def test_build_zone_periods_rejects_an_unrecognised_sentiment_label() -> None:
    snapshots = [_snapshot("2026-08-02", "Euphoria", 7000.0)]

    with pytest.raises(ValueError, match="Euphoria"):
        build_zone_periods(snapshots)
