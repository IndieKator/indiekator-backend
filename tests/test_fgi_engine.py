from datetime import date

import numpy as np
import pandas as pd

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
        {
            "trend_ihsg": 75,
            "trend_idx_composite": 75,
            "trend_indeks_harga_saham_gabungan": 75,
        },
        index=week_dates,
    )

    monkeypatch.setattr(fgi_engine, "fetch_ihsg_prices", lambda _: prices)
    monkeypatch.setattr(fgi_engine, "fetch_fgi_google_trends", lambda *_: trends)

    result = fgi_engine.compute_fgi(as_of=date(2025, 9, 1))

    latest = result.iloc[-1]
    assert latest["price_score"] > 50
    assert latest["search_score"] == 75
    assert latest["fgi"] == round(0.6 * latest["price_score"] + 0.4 * 75, 2)
    assert latest["sentiment"] in {"Greed", "Extreme Greed"}
