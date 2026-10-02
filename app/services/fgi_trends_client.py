from datetime import date
import re

import pandas as pd
from pytrends_modern import TrendReq

FGI_INDEX_NAME = "ihsg"
FGI_KEYWORDS = (
    "ihsg",
    "idx composite",
    "indeks harga saham gabungan",
)
MAX_KEYWORDS_PER_REQUEST = 5
MAX_KEYWORD_LENGTH = 100


def normalize_keywords(keywords: list[str] | tuple[str, ...]) -> list[str]:
    """Return validated, de-duplicated Google Trends terms in request order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_keyword in keywords:
        keyword = re.sub(r"\s+", " ", raw_keyword.strip().lower())
        if not keyword or len(keyword) > MAX_KEYWORD_LENGTH:
            raise ValueError("Each keyword must contain 1 to 100 characters")
        if keyword not in seen:
            normalized.append(keyword)
            seen.add(keyword)

    if not normalized:
        raise ValueError("Provide at least one Google Trends keyword")
    if len(normalized) > MAX_KEYWORDS_PER_REQUEST:
        raise ValueError(f"Select at most {MAX_KEYWORDS_PER_REQUEST} keywords")
    return normalized


def fetch_google_trends(
    keywords: list[str] | tuple[str, ...], start_date: date, end_date: date
) -> pd.DataFrame:
    """Fetch independently scaled Google Trends observations in long form."""
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")

    normalized = normalize_keywords(keywords)
    trends = TrendReq(hl="id-ID", tz=0, retries=3, backoff_factor=0.5)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"
    frames: list[pd.DataFrame] = []

    for keyword in normalized:
        trends.build_payload([keyword], timeframe=timeframe, geo="ID")
        frame = trends.interest_over_time()
        if frame.empty:
            raise RuntimeError(f"Google Trends returned no data for '{keyword}'")

        frame = frame.drop(columns=["isPartial"], errors="ignore").reset_index()
        date_column = frame.columns[0]
        frame = frame.rename(columns={date_column: "date", keyword: "score"})
        frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None).dt.normalize()
        frame["keyword"] = keyword
        frames.append(frame[["date", "keyword", "score"]])

    return pd.concat(frames, ignore_index=True).sort_values(["date", "keyword"])


def trend_to_records(
    dataframe: pd.DataFrame,
    index_name: str = FGI_INDEX_NAME,
) -> list[dict[str, str | float]]:
    """Serialize a long-form Trends frame for the trend_snapshots upsert."""
    records: list[dict[str, str | float]] = []
    for row in dataframe.itertuples(index=False):
        records.append(
            {
                "date": pd.Timestamp(row.date).date().isoformat(),
                "index_name": index_name,
                "keyword": str(row.keyword),
                "score": round(float(row.score), 2),
            }
        )
    return records
