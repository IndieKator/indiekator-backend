import pandas as pd

from app.services.sectors_client import fetch_ihsg_prices
from app.services.trends_client import fetch_google_trends
from app.services.zones import score_to_zone


def compute_sentiment(lookback_days: int = 365) -> pd.DataFrame:
    ihsg_df = fetch_ihsg_prices(lookback_days)
    trends_df = fetch_google_trends()

    ihsg_df["MA_125"] = ihsg_df["Close"].rolling(window=125).mean()

    trends_df.index = pd.to_datetime(trends_df.index)
    min_date = trends_df.index.min()
    max_date = trends_df.index.max() + pd.Timedelta(days=6)
    daily_trends = trends_df.reindex(
        pd.date_range(start=min_date, end=max_date, freq="D")
    )
    daily_trends["ihsg"] = daily_trends["ihsg"].ffill()

    merged = pd.merge(
        ihsg_df,
        daily_trends[["ihsg"]],
        left_index=True,
        right_index=True,
        how="inner",
    )
    merged.dropna(subset=["MA_125"], inplace=True)

    min_trend = merged["ihsg"].min()
    max_trend = merged["ihsg"].max()
    if max_trend - min_trend == 0:
        merged["Normalized_Trends"] = 50.0
    else:
        merged["Normalized_Trends"] = (
            (merged["ihsg"] - min_trend) / (max_trend - min_trend)
        ) * 100

    merged["Arah_Momentum"] = (merged["Close"] > merged["MA_125"]).astype(int).replace(
        0, -1
    )

    def calc_skala(row: pd.Series) -> float:
        nt = row["Normalized_Trends"]
        if row["Arah_Momentum"] == 1:
            return (nt / 100) * 50 + 50
        return 50 - (nt / 100) * 50

    merged["Skala_Emosi"] = merged.apply(calc_skala, axis=1).clip(0, 100)
    merged["zone"] = merged["Skala_Emosi"].apply(lambda s: score_to_zone(s)[0])

    return merged


def sentiment_to_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for idx, row in df.iterrows():
        records.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "close_price": float(row["Close"]),
                "ma_125": float(row["MA_125"]),
                "google_trends_raw": int(row["ihsg"]),
                "normalized_trends": round(float(row["Normalized_Trends"]), 2),
                "arah_momentum": int(row["Arah_Momentum"]),
                "skala_emosi": round(float(row["Skala_Emosi"]), 2),
                "zone": row["zone"],
            }
        )
    return records
