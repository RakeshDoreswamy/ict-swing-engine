"""Free official NSE data: the equity list and daily bhavcopy files.

Bhavcopy = NSE's end-of-day file for every listed security (open/high/low/close, volume,
traded value). It is the most accurate free daily source. Two file formats exist:

* UDiFF (from July 2024): BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
  columns TradDt, TckrSymb, SctySrs, OpnPric, HghPric, LwPric, ClsPric, TtlTradgVol, TtlTrfVal ...
* Legacy: cmDDMONYYYYbhav.csv.zip
  columns SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP ...

``parse_bhavcopy`` reads either into one normalised table.
"""
from __future__ import annotations

import io
import time
import zipfile
from datetime import date, timedelta

import pandas as pd

UDIFF_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
LEGACY_URL = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{y}/{mon}/cm{d}{mon}{y}bhav.csv.zip"
EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Referer": "https://www.nseindia.com/",
           "Accept": "*/*"}
COLS = ["date", "symbol", "series", "open", "high", "low", "close", "volume", "turnover"]


def parse_bhavcopy(raw: bytes | str, series: tuple = ("EQ", "BE")) -> pd.DataFrame:
    """Parse a bhavcopy CSV (or zip) in either format. turnover is in rupees."""
    if isinstance(raw, bytes) and raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(z.namelist()[0])
    text = raw.decode() if isinstance(raw, bytes) else raw
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    if "TckrSymb" in df.columns:  # UDiFF
        out = pd.DataFrame({
            "date": pd.to_datetime(df["TradDt"]), "symbol": df["TckrSymb"].str.strip(),
            "series": df["SctySrs"].astype(str).str.strip(), "open": df["OpnPric"], "high": df["HghPric"],
            "low": df["LwPric"], "close": df["ClsPric"], "volume": df["TtlTradgVol"], "turnover": df["TtlTrfVal"]})
    else:  # legacy
        out = pd.DataFrame({
            "date": pd.to_datetime(df["TIMESTAMP"], format="%d-%b-%Y"), "symbol": df["SYMBOL"].str.strip(),
            "series": df["SERIES"].astype(str).str.strip(), "open": df["OPEN"], "high": df["HIGH"],
            "low": df["LOW"], "close": df["CLOSE"], "volume": df["TOTTRDQTY"], "turnover": df["TOTTRDVAL"]})
    out = out[out["series"].isin(series)]
    for c in ("open", "high", "low", "close", "volume", "turnover"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.dropna(subset=["close"])[COLS].reset_index(drop=True)


def _session():
    import requests

    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)  # sets cookies NSE sometimes expects
    except Exception:
        pass
    return s


def fetch_bhavcopy(d: date, session=None, series=("EQ", "BE")) -> pd.DataFrame | None:
    """Download one day's bhavcopy. Returns None on holidays / missing files."""
    s = session or _session()
    urls = [UDIFF_URL.format(ymd=d.strftime("%Y%m%d")),
            LEGACY_URL.format(y=d.strftime("%Y"), mon=d.strftime("%b").upper(), d=d.strftime("%d"))]
    for url in urls:
        try:
            r = s.get(url, timeout=20)
        except Exception:
            continue
        if r.status_code == 200 and r.content[:2] == b"PK":
            return parse_bhavcopy(r.content, series)
    return None


def fetch_bhavcopy_range(start: date, end: date, have: set | None = None, series=("EQ", "BE"),
                         pause: float = 0.3, log=print) -> pd.DataFrame:
    """Download every trading day in [start, end] not already in ``have`` (a set of dates)."""
    s = _session()
    frames, d = [], start
    have = have or set()
    while d <= end:
        if d.weekday() < 5 and d not in have:
            df = fetch_bhavcopy(d, s, series)
            if df is not None:
                frames.append(df)
                log(f"  bhavcopy {d}: {len(df)} rows")
            time.sleep(pause)
        d += timedelta(days=1)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)


def load_equity_list(path, series=("EQ", "BE")) -> pd.DataFrame:
    """Read NSE's EQUITY_L.csv (SYMBOL, NAME OF COMPANY, SERIES, ...)."""
    df = pd.read_csv(path)
    df.columns = [c.strip().upper() for c in df.columns]
    df["SYMBOL"] = df["SYMBOL"].str.strip()
    df["SERIES"] = df["SERIES"].astype(str).str.strip()
    return df[df["SERIES"].isin(series)].reset_index(drop=True)


def download_equity_list(dest) -> None:
    s = _session()
    r = s.get(EQUITY_LIST_URL, timeout=20)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        fh.write(r.content)
