"""Is today's data in? Used by unattended runs (GitHub Actions, launchd) before scanning.

NIFTY's daily bar from Yahoo tells us whether NSE traded today (it covers weekends AND exchange
holidays without a holiday table). The stock panel must then reach that same date.
"""
from __future__ import annotations

import pandas as pd

IST = "Asia/Kolkata"


def today_ist() -> pd.Timestamp:
    return pd.Timestamp.now(tz=IST).tz_localize(None).normalize()


def status(panel_last, index_last, today) -> tuple[str, str]:
    """Return (state, message). state: "ok" | "closed" | "stale"."""
    today = pd.Timestamp(today).normalize()
    if index_last is None or pd.isna(index_last):
        return "stale", "No NIFTY index data, so it is unknown whether NSE traded today."
    index_last = pd.Timestamp(index_last).normalize()
    if index_last < today:
        return "closed", (f"NSE did not trade on {today:%a %d %b %Y} (weekend or exchange holiday): "
                          f"last session {index_last:%d %b}. Nothing new to scan.")
    if panel_last is None or pd.isna(panel_last) or pd.Timestamp(panel_last).normalize() < index_last:
        last = "none" if panel_last is None or pd.isna(panel_last) else f"{pd.Timestamp(panel_last):%d %b}"
        return "stale", (f"NSE traded on {index_last:%d %b} but the stock bars stop at {last} "
                         f"(bhavcopy not published yet and the Yahoo top-up failed). Re-run later.")
    return "ok", f"Data complete for {index_last:%a %d %b %Y}."
