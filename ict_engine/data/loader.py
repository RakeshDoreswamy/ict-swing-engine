"""Pluggable OHLCV data layer.

Every loader returns a DataFrame indexed by a DatetimeIndex named ``date`` with
float columns ``open, high, low, close, volume``, sorted oldest first.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ict_engine.config import ROOT

COLS = ["open", "high", "low", "close", "volume"]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    df = df[COLS].astype(float).sort_index()
    return df[~df.index.duplicated(keep="last")]


def load_csv(symbol: str, csv_dir: str | Path = "data/raw") -> pd.DataFrame:
    path = Path(csv_dir)
    if not path.is_absolute():
        path = ROOT / path
    return _normalise(pd.read_csv(path / f"{symbol}.csv"))


def load_yfinance(symbol: str, start: str, suffix: str = ".NS") -> pd.DataFrame:
    import yfinance as yf  # optional dependency

    ticker = "^NSEI" if symbol == "NIFTY" else f"{symbol}{suffix}"
    raw = yf.download(ticker, start=start, progress=False, auto_adjust=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return _normalise(raw.reset_index().rename(columns={"Date": "date"}))


def load(symbol: str, cfg: dict) -> pd.DataFrame:
    """Load daily bars for ``symbol`` using the source named in config."""
    d = cfg["data"]
    if d["source"] == "csv":
        return load_csv(symbol, d["csv_dir"])
    if d["source"] == "yfinance":
        return load_yfinance(symbol, d["start"], d["yfinance_suffix"])
    raise ValueError(f"Unknown data source {d['source']!r}")


def to_weekly(daily: pd.DataFrame, rule: str = "W-FRI") -> pd.DataFrame:
    """Resample daily bars to weekly. A weekly bar is labelled by its last trading day."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    wk = daily.resample(rule).agg(agg).dropna(subset=["open"])
    last_day = daily.index.to_series().resample(rule).last().dropna()
    wk.index = pd.DatetimeIndex(last_day.loc[wk.index].values, name="date")
    return wk
