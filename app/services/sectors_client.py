import time
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

from app.config import get_settings

INDEX_CODE = "ihsg"
CHUNK_DAYS = 89
DEFAULT_LOOKBACK_DAYS = 365


def fetch_ihsg_prices(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> pd.DataFrame:
    settings = get_settings()
    api_url = f"https://api.sectors.app/v2/index-daily/{INDEX_CODE}/"
    headers = {"Authorization": settings.sectors_api_key}

    # Sectors validates dates against its UTC trading-day boundary. Using a
    # local naive timestamp can request tomorrow's date in UTC+ timezones.
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=lookback_days)
    all_data: list[dict] = []
    current_end = end_date

    while current_end > start_date:
        current_start = max(current_end - timedelta(days=CHUNK_DAYS), start_date)
        params = {
            "start": current_start.strftime("%Y-%m-%d"),
            "end": current_end.strftime("%Y-%m-%d"),
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            chunk_data = response.json()

        if isinstance(chunk_data, list) and chunk_data:
            all_data.extend(chunk_data)
        else:
            break

        current_end = current_start - timedelta(days=1)
        time.sleep(0.5)

    if not all_data:
        raise RuntimeError("Failed to fetch IHSG price data from Sectors API")

    df = pd.DataFrame(all_data)
    df["date"] = pd.to_datetime(df["date"])
    df.drop_duplicates(subset=["date"], inplace=True)
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    return df[["price"]].rename(columns={"price": "Close"})
