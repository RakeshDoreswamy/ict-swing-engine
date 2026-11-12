"""Free Yahoo Finance data via yfinance.

* Daily bars for indices (^NSEI NIFTY 50, ^CRSLDX NIFTY 500, ^INDIAVIX) and, as a fallback, stocks.
* 15-minute bars for stocks: Yahoo keeps only the LAST 60 DAYS of 15m data, so the scanner caches
  every download and merges it (data/store/m15), building a longer history over time.
Timestamps are converted to naive Asia/Kolkata time.
"""
from __future__ import annotations

import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]


def _yf():
    import yfinance as yf  # imported lazily so tests run without it

    return yf


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("Asia/Kolkata").tz_localize(None)
    df.index = idx
    df.index.name = "date"
    df = df[[c for c in OHLCV if c in df.columns]].astype(float)
    return df.dropna(subset=["close"]).sort_index()


def _split(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    if isinstance(raw.columns, pd.MultiIndex):
        lvl0 = raw.columns.get_level_values(0)
        for t in tickers:
            if t in lvl0:
                sub = _norm(raw[t])
                if not sub.empty:
                    out[t] = sub
    elif len(tickers) == 1 and not raw.empty:
        out[tickers[0]] = _norm(raw)
    return out


def daily(tickers: list[str], start: str) -> dict[str, pd.DataFrame]:
    raw = _yf().download(tickers, start=start, interval="1d", group_by="ticker",
                         auto_adjust=False, threads=True, progress=False)
    return _split(raw, tickers)


def intraday_15m(symbols: list[str], period: str = "60d", chunk: int = 50) -> dict[str, pd.DataFrame]:
    """15-minute bars for NSE symbols (adds the .NS suffix). Downloads in chunks."""
    return intraday(symbols, "15m", period, chunk)


def intraday(symbols: list[str], interval: str = "15m", period: str = "60d", chunk: int = 50,
             log=None) -> dict[str, pd.DataFrame]:
    """Intraday bars for NSE symbols. Yahoo limits: 15m → 60 days, 60m → 730 days."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        tickers = [f"{s}.NS" for s in part]
        raw = _yf().download(tickers, period=period, interval=interval, group_by="ticker",
                             auto_adjust=False, threads=True, progress=False)
        for t, df in _split(raw, tickers).items():
            # drop the bar still forming (Yahoo includes it during market hours)
            out[t[:-3]] = df
        if log:
            log(f"  {interval}: {min(i + chunk, len(symbols))}/{len(symbols)} symbols")
    return out
