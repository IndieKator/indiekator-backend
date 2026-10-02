from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services import fgi_engine


def test_classify_fgi_uses_logic_py_boundaries() -> None:
    assert fgi_engine.classify_fgi(25) == "Extreme Fear"
    assert fgi_engine.classify_fgi(25.01) == "Fear"
    assert fgi_engine.classify_fgi(45.01) == "Neutral"
    assert fgi_engine.classify_fgi(55.01) == "Greed"
    assert fgi_engine.classify_fgi(75.01) == "Extreme Greed"


def test_compute_fgi_uses_weighted_price_and_search_scores(monkeypatch) -> None:
    dates = pd.date_range("2025-01-01", periods=180, freq="B")
    prices = pd.DataFrame({"Close": np.linspace(100.0, 130.0, len(dates))}, index=dates)
    week_dates = prices.resample("W-SUN").last().index
    trends = pd.DataFrame(
        [
            {"date": week_date, "keyword": keyword, "score": 75}
            for week_date in week_dates
            for keyword in fgi_engine.FGI_KEYWORDS
        ]
    )

    monkeypatch.setattr(fgi_engine, "fetch_ihsg_prices", lambda _: prices)
    monkeypatch.setattr(fgi_engine, "fetch_google_trends", lambda *_: trends)

    result = fgi_engine.compute_fgi(as_of=date(2025, 9, 1))

    latest = result.iloc[-1]
    assert latest["price_score"] > 50
    assert latest["search_score"] == 75
    assert latest["fgi"] == round(0.6 * latest["price_score"] + 0.4 * 75, 2)
    assert latest["sentiment"] in {"Greed", "Extreme Greed"}


def test_compute_fgi_uses_30_period_moving_average(monkeypatch) -> None:
    dates = pd.date_range("2025-01-01", periods=180, freq="B")
    closes = np.linspace(100.0, 130.0, len(dates)) + np.sin(np.arange(len(dates)))
    prices = pd.DataFrame({"Close": closes}, index=dates)
    week_dates = prices.resample("W-SUN").last().index
    trends = pd.DataFrame(
        [
            {"date": week_date, "keyword": keyword, "score": 60}
            for week_date in week_dates
            for keyword in fgi_engine.FGI_KEYWORDS
        ]
    )

    monkeypatch.setattr(fgi_engine, "fetch_ihsg_prices", lambda _: prices)
    monkeypatch.setattr(fgi_engine, "fetch_google_trends", lambda *_: trends)

    result = fgi_engine.compute_fgi(as_of=date(2025, 9, 1))

    assert fgi_engine.MA_WINDOW == 30
    assert "ma_30" in result.columns
    assert "ma_125" not in result.columns

    week_end = result.index[-1]
    last_closes = prices.loc[:week_end, "Close"].tail(30)
    assert result.loc[week_end, "ma_30"] == pytest.approx(last_closes.mean())


def test_fgi_to_records_emits_ma_30(monkeypatch) -> None:
    dates = pd.date_range("2025-01-01", periods=180, freq="B")
    prices = pd.DataFrame({"Close": np.linspace(100.0, 130.0, len(dates))}, index=dates)
    week_dates = prices.resample("W-SUN").last().index
    trends = pd.DataFrame(
        [
            {"date": week_date, "keyword": keyword, "score": 60}
            for week_date in week_dates
            for keyword in fgi_engine.FGI_KEYWORDS
        ]
    )

    monkeypatch.setattr(fgi_engine, "fetch_ihsg_prices", lambda _: prices)
    monkeypatch.setattr(fgi_engine, "fetch_google_trends", lambda *_: trends)

    records = fgi_engine.fgi_to_records(fgi_engine.compute_fgi(as_of=date(2025, 9, 1)))

    assert records
    assert all("ma_30" in record and "ma_125" not in record for record in records)
