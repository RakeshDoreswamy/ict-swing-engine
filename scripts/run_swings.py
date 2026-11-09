"""Module 1 demo: institutional swing points on daily + weekly bars.

Usage: python -m scripts.run_swings NIFTY
"""
from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ict_engine.config import ROOT, load_config
from ict_engine.data.loader import load, to_weekly
from ict_engine.detectors.swings import swing_table

MARK = {1: ("v", 30), 2: ("v", 70), 3: ("*", 220)}


def plot(df, tab, title, path):
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(df.index, df["close"], lw=0.9, color="#555")
    ax.vlines(df.index, df["low"], df["high"], lw=0.5, color="#aaa")
    for _, r in tab.iterrows():
        m, s = MARK[r.level]
        colour = "#c0392b" if r.side == "high" else "#27ae60"
        ax.scatter(r.date, r.price, marker=m if r.side == "high" else "^", s=s, color=colour, zorder=3)
        if r.unbroken and r.level >= 2:
            ax.hlines(r.price, r.date, df.index[-1], colors=colour, linestyles=":", lw=0.8)
            ax.annotate(f"{r.type} {r.price:,.0f}", (df.index[-1], r.price), fontsize=7, color=colour)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(symbol: str = "NIFTY"):
    cfg = load_config()
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    daily = load(symbol, cfg)
    weekly = to_weekly(daily, cfg["data"]["weekly_rule"])
    for tf, df in (("daily", daily), ("weekly", weekly)):
        tab = swing_table(df, cfg)
        tab.drop(columns="bar").to_csv(out / f"{symbol}_{tf}_swings.csv", index=False)
        plot(df, tab, f"{symbol} {tf} institutional swing points", out / f"{symbol}_{tf}_swings.png")
        print(f"\n=== {symbol} {tf}: {len(df)} bars, {df.index[0].date()} to {df.index[-1].date()} ===")
        print(tab.groupby(["type", "unbroken"]).size().unstack(fill_value=0))
        key = tab[(tab.level >= 2)].tail(8)[["date", "type", "price", "unbroken", "broken_date"]]
        print(key.to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NIFTY")
