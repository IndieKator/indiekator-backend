from datetime import date

import pandas as pd
from pytrends_modern import TrendReq

FGI_KEYWORDS: dict[str, str] = {
    "ihsg": "trend_ihsg",
    "idx composite": "trend_idx_composite",
    "indeks harga saham gabungan": "trend_indeks_harga_saham_gabungan",
}


def fetch_fgi_google_trends(start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch each FGI keyword independently, preserving its Google Trends scale."""
    trends = TrendReq(hl="id-ID", tz=0, retries=3, backoff_factor=0.5)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"
    frames: list[pd.DataFrame] = []

    for keyword, column_name in FGI_KEYWORDS.items():
        trends.build_payload([keyword], timeframe=timeframe, geo="ID")
        frame = trends.interest_over_time()
        if frame.empty:
            raise RuntimeError(f"Google Trends returned no data for '{keyword}'")

        frame = frame.drop(columns=["isPartial"], errors="ignore")
        frame.index = pd.to_datetime(frame.index)
        if frame.index.tz is not None:
            frame.index = frame.index.tz_localize(None)
        frame.index = frame.index.normalize()
        frames.append(frame[[keyword]].rename(columns={keyword: column_name}))

    return pd.concat(frames, axis=1, join="inner").sort_index()
