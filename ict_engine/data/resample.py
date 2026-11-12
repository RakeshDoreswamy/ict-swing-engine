"""Session-anchored resampling of NSE intraday bars.

NSE cash session: 09:15–15:30 (375 minutes). 45-minute candles anchored at 09:15 give 8 full
candles (09:15, 10:00, 10:45, 11:30, 12:15, 13:00, 13:45, 14:30) plus a 15-minute leftover
(15:15–15:30).

* merge_last_partial=True  (default): the leftover joins the 14:30 candle → 8 candles per day,
  the last one 14:30–15:30.
* merge_last_partial=False: the leftover is its own 9th candle (what TradingView shows).

Each candle is labelled by its start time. Candles never span two sessions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample_session(df: pd.DataFrame, minutes: int = 45, anchor: str = "09:15",
                     session_end: str = "15:30", merge_last_partial: bool = True) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    idx = df.index
    day = idx.normalize()
    a_h, a_m = map(int, anchor.split(":"))
    e_h, e_m = map(int, session_end.split(":"))
    start = day + pd.Timedelta(hours=a_h, minutes=a_m)
    mins = np.asarray((idx - start) / pd.Timedelta(minutes=1)).astype(int)
    bucket = mins // minutes
    if merge_last_partial:
        session_len = (e_h * 60 + e_m) - (a_h * 60 + a_m)
        n_full = max(session_len // minutes, 1)
        bucket = np.minimum(bucket, n_full - 1)
    label = start + pd.to_timedelta(bucket * minutes, unit="m")
    cols = {k: v for k, v in AGG.items() if k in df.columns}
    out = df.groupby(label).agg(cols)
    out.index.name = "date"
    return out.dropna(subset=["close"])


def to_45m(m15: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    r = (cfg or {}).get("scan", {}).get("resample_45m", {})
    return resample_session(m15, 45, r.get("anchor", "09:15"), "15:30", r.get("merge_last_partial", True))
