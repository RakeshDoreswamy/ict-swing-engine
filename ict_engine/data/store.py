"""Local cache for market data.

Layout under ``store_dir`` (default data/store):
    daily_panel.<ext>        long table: date, symbol, open, high, low, close, volume, turnover
    index/<NAME>.<ext>       daily bars for indices (NIFTY 50, NIFTY 500, India VIX)
    m15/<SYMBOL>.<ext>       15-minute bars, merged incrementally (Yahoo keeps only 60 days)

Parquet is used when ``pyarrow`` is installed, otherwise gzip CSV. Both are read transparently.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ict_engine.config import ROOT

try:  # pragma: no cover - depends on the environment
    import pyarrow  # noqa: F401

    EXT = ".parquet"
except ImportError:  # pragma: no cover
    EXT = ".csv.gz"


class Store:
    def __init__(self, root: str | Path = "data/store"):
        root = Path(root)
        self.root = root if root.is_absolute() else ROOT / root
        for sub in ("index", "m15"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # -- low level ---------------------------------------------------------
    @staticmethod
    def _read(path: Path) -> pd.DataFrame | None:
        stem = str(path)
        for ext in (".parquet", ".csv.gz"):
            p = Path(stem + ext)
            if p.exists():
                if ext == ".parquet":
                    return pd.read_parquet(p)
                return pd.read_csv(p, parse_dates=["date"])
        return None

    @staticmethod
    def _write(df: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if EXT == ".parquet":
            df.to_parquet(str(path) + EXT, index=False)
        else:
            df.to_csv(str(path) + EXT, index=False)

    # -- daily panel -------------------------------------------------------
    def read_daily_panel(self) -> pd.DataFrame:
        df = self._read(self.root / "daily_panel")
        if df is None:
            return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume", "turnover"])
        df["date"] = pd.to_datetime(df["date"])
        return df

    def write_daily_panel(self, df: pd.DataFrame) -> None:
        df = df.drop_duplicates(["date", "symbol"], keep="last").sort_values(["symbol", "date"])
        self._write(df.reset_index(drop=True), self.root / "daily_panel")

    def merge_daily_panel(self, new: pd.DataFrame) -> pd.DataFrame:
        merged = pd.concat([self.read_daily_panel(), new], ignore_index=True)
        self.write_daily_panel(merged)
        return self.read_daily_panel()

    # -- per-symbol series (index daily, 15m) ------------------------------
    def read_series(self, kind: str, name: str) -> pd.DataFrame | None:
        df = self._read(self.root / kind / name)
        if df is None or df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

    def merge_series(self, kind: str, name: str, new: pd.DataFrame) -> pd.DataFrame:
        old = self.read_series(kind, name)
        df = new if old is None else pd.concat([old, new])
        df = df[~df.index.duplicated(keep="last")].sort_index()
        out = df.reset_index().rename(columns={"index": "date"})
        self._write(out, self.root / kind / name)
        return df
