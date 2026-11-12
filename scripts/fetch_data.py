"""Download free market data into data/store (run this on your own Mac: it needs internet).

    python -m scripts.fetch_data --universe            # NSE equity list → data/universe/EQUITY_L.csv
    python -m scripts.fetch_data --daily               # NSE bhavcopy, incremental (official, free)
    python -m scripts.fetch_data --indices             # NIFTY 50, NIFTY 500, India VIX (Yahoo)
    python -m scripts.fetch_data --all                 # all three
    python -m scripts.fetch_data --m15 RELIANCE TCS    # 15m bars for chosen symbols (Yahoo, last 60 days)
    python -m scripts.fetch_data --daily --source yfinance   # daily from Yahoo instead of bhavcopy
    python -m scripts.fetch_data --daily --days 730          # longer history for the walk-forward
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import pandas as pd

from ict_engine.config import ROOT, load_config
from ict_engine.data.providers import nse, yahoo
from ict_engine.data.store import Store


def _yf_daily(cfg, start) -> pd.DataFrame:
    sc = cfg["scan"]
    uni = nse.load_equity_list(ROOT / sc["universe_file"], tuple(sc["series"]))
    syms = uni.SYMBOL.tolist()
    frames = []
    for i in range(0, len(syms), 100):
        part = [f"{s}.NS" for s in syms[i:i + 100]]
        for t, df in yahoo.daily(part, str(start)).items():
            df = df.reset_index()
            df["symbol"] = t[:-3]
            df["turnover"] = df.close * df.volume
            frames.append(df)
        print(f"  yfinance daily {min(i + 100, len(syms))}/{len(syms)}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_daily(cfg, store, source, days=None):
    sc = cfg["scan"]
    panel = store.read_daily_panel()
    end = date.today()
    start = end - timedelta(days=int(days or sc["daily_lookback_days"] * 1.45))
    if source == "bhavcopy":
        have = set(pd.to_datetime(panel.date).dt.date.unique()) if len(panel) else set()
        new = nse.fetch_bhavcopy_range(start, end, have, tuple(sc["series"]))
        if new.empty and not have:
            print("Bhavcopy download returned nothing (NSE may be blocking this network): using Yahoo instead.")
            new = _yf_daily(cfg, start)
        elif len(new):
            new = new.drop(columns=["series"])
    else:
        new = _yf_daily(cfg, start)
    if len(new):
        store.merge_daily_panel(new)
    top_up_daily(cfg, store)
    merged = store.read_daily_panel()
    if len(merged):
        print(f"Daily panel: {merged.symbol.nunique()} symbols, {merged.date.min():%d %b %Y} → {merged.date.max():%d %b %Y}")


def top_up_daily(cfg, store):
    """If NIFTY has a newer session than the stock panel (bhavcopy not out yet), fill the gap from Yahoo."""
    idx = store.read_series("index", "nifty50")
    panel = store.read_daily_panel()
    if idx is None or panel.empty:
        return
    last_idx, last_panel = idx.index.max().normalize(), panel.date.max().normalize()
    if last_panel >= last_idx:
        return
    print(f"Stock bars end {last_panel:%d %b}, NIFTY has {last_idx:%d %b}: topping up from Yahoo…")
    new = _yf_daily(cfg, (last_panel + pd.Timedelta(days=1)).date())
    if len(new):
        new = new[pd.to_datetime(new["date"]).dt.normalize() > last_panel]
        store.merge_daily_panel(new)


def fetch_indices(cfg, store):
    sc = cfg["scan"]
    start = (date.today() - timedelta(days=int(sc["daily_lookback_days"] * 1.45))).isoformat()
    tick = sc["indices"]
    got = yahoo.daily(list(tick.values()), start)
    for name, t in tick.items():
        if t in got:
            store.merge_series("index", name, got[t])
            print(f"  {name} ({t}): {len(got[t])} bars")
        else:
            print(f"  {name} ({t}): no data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--indices", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source", choices=["bhavcopy", "yfinance"])
    ap.add_argument("--m15", nargs="*")
    ap.add_argument("--days", type=int, help="calendar days of daily history (walk-forward needs ~700)")
    a = ap.parse_args()
    cfg = load_config()
    store = Store(cfg["scan"]["store_dir"])
    if a.universe or a.all:
        dest = ROOT / cfg["scan"]["universe_file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        nse.download_equity_list(dest)
        print(f"Universe: {len(nse.load_equity_list(dest))} EQ/BE symbols → {dest.relative_to(ROOT)}")
    if a.indices or a.all:          # first: NIFTY's last bar tells the daily step whether NSE traded today
        fetch_indices(cfg, store)
    if a.daily or a.all:
        fetch_daily(cfg, store, a.source or cfg["scan"]["daily_source"], a.days)
    if a.m15:
        for sym, df in yahoo.intraday_15m(a.m15).items():
            out = store.merge_series("m15", sym, df)
            print(f"  {sym}: {len(out)} 15m bars ({out.index[0]:%d %b} → {out.index[-1]:%d %b %H:%M})")


if __name__ == "__main__":
    main()
