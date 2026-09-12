import pandas as pd
from pytrends_modern import TrendReq

KEYWORD = "ihsg"
TIMEFRAME = "today 12-m"


def fetch_google_trends() -> pd.DataFrame:
    pytrends = TrendReq(hl="id-ID", tz=420)
    pytrends.build_payload([KEYWORD], timeframe=TIMEFRAME)
    df = pytrends.interest_over_time()

    if df.empty:
        raise RuntimeError("Google Trends returned no data for 'ihsg'")

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    df.index = pd.to_datetime(df.index)
    return df[[KEYWORD]].rename(columns={KEYWORD: "ihsg"})
