from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from app.services.fgi_trends_client import FGI_KEYWORDS, fetch_google_trends
from app.services.sectors_client import fetch_ihsg_prices

FGI_LOOKBACK_MONTHS = 18

# Component weights. Exposed as constants so the API breakdown reports the same
# weights the engine actually applies, rather than a second hardcoded copy that
# can drift.
PRICE_WEIGHT = 0.60
SEARCH_WEIGHT = 0.40

# Rolling window (in daily closes) for the moving average stored as ``ma_30``.
MA_WINDOW = 30

LEGACY_TREND_COLUMNS = {
    "ihsg": "trend_ihsg",
    "idx composite": "trend_idx_composite",
    "indeks harga saham gabungan": "trend_indeks_harga_saham_gabungan",
}


def classify_fgi(value: float) -> str:
    if value <= 25:
        return "Extreme Fear"
    if value <= 45:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 75:
        return "Greed"
    return "Extreme Greed"


def calculate_keyword_fgi(
    price_score: float,
    distance_pct: float,
    trend_score: float,
) -> tuple[float, float]:
    """Return search and FGI scores when one keyword supplies search interest."""
    market_direction = float(np.sign(distance_pct))
    search_score = float(np.clip(50 + (trend_score - 50) * market_direction, 0, 100))
    fgi_score = round(PRICE_WEIGHT * price_score + SEARCH_WEIGHT * search_score, 2)
    return round(search_score, 2), fgi_score


def compute_fgi(as_of: date | None = None) -> pd.DataFrame:
    """Calculate weekly FGI and retain its source trend observations in attrs."""
    end_date = as_of or datetime.now(timezone.utc).date()
    start_date = (pd.Timestamp(end_date) - pd.DateOffset(months=FGI_LOOKBACK_MONTHS)).date()
    lookback_days = (end_date - start_date).days + 1

    prices = fetch_ihsg_prices(lookback_days).copy()
    prices["ma_30"] = prices["Close"].rolling(window=MA_WINDOW).mean()
    weekly_prices = prices[["Close", "ma_30"]].resample("W-SUN").last().dropna()

    trend_snapshots = fetch_google_trends(FGI_KEYWORDS, start_date, end_date)
    trends = trend_snapshots.pivot(index="date", columns="keyword", values="score")
    weekly = weekly_prices.join(trends, how="inner").dropna(subset=list(FGI_KEYWORDS))
    if weekly.empty:
        raise RuntimeError("No overlapping weekly IHSG and Google Trends data for FGI")

    weekly["trends_mean"] = weekly[list(FGI_KEYWORDS)].mean(axis=1)
    weekly["distance_pct"] = ((weekly["Close"] - weekly["ma_30"]) / weekly["ma_30"]) * 100
    weekly["price_score"] = (50 + (weekly["distance_pct"] / 6.0) * 50).clip(0, 100)
    market_direction = np.sign(weekly["distance_pct"])
    weekly["search_score"] = (50 + (weekly["trends_mean"] - 50) * market_direction).clip(0, 100)
    weekly["fgi"] = (
        PRICE_WEIGHT * weekly["price_score"] + SEARCH_WEIGHT * weekly["search_score"]
    ).round(2)
    weekly["sentiment"] = weekly["fgi"].map(classify_fgi)

    result = weekly.rename(columns={"Close": "close_price"})
    result.attrs["trend_snapshots"] = trend_snapshots
    return result


def fgi_to_records(
    dataframe: pd.DataFrame,
    updated_at: datetime | None = None,
) -> list[dict]:
    refreshed_at = updated_at or datetime.now(timezone.utc)
    record_columns = [
        "close_price",
        "ma_30",
        "distance_pct",
        "price_score",
        "search_score",
        "fgi",
        "sentiment",
        "trends_mean",
    ]
    records: list[dict] = []
    for week_date, row in dataframe.iterrows():
        record = {
            "week_date": pd.Timestamp(week_date).date().isoformat(),
            "updated_at": refreshed_at.isoformat(),
        }
        for column in record_columns:
            value = row[column]
            record[column] = value if column == "sentiment" else round(float(value), 2)
        for keyword, column in LEGACY_TREND_COLUMNS.items():
            record[column] = round(float(row[keyword]), 2)
        records.append(record)
    return records
