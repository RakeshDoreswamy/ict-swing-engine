"""Interactive concept walkthroughs on real data.

Usage:
    python -m scripts.learn                      # list concepts
    python -m scripts.learn swings               # last 30 NIFTY daily bars
    python -m scripts.learn swings --bars 60 --symbol RELIANCE --tf weekly
"""
from __future__ import annotations

import argparse

import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ict_engine.config import ROOT, load_config
from ict_engine.data.loader import load, to_weekly
from ict_engine.detectors.swings import detect_swings, swing_table

CONCEPTS = {
    "swings": "1-3  Swing points (STH/STL), institutional levels (ITH/LTH), open float",
}
PLANNED = [
    "pools (M2)", "sweeps (M2)", "fvg (M3)", "orderblocks (M3)", "premium-discount (M4)",
    "ote (M4)", "ipda (M5)", "bias (M6)", "mss (M7)", "entries (M8)",
]


def _fmt(x):
    return f"{x:,.2f}"


def learn_swings(df, cfg, symbol, tf, bars):
    # Detect on FULL history (levels need distant neighbours), then display the window.
    ev = detect_swings(df, cfg)
    tab_full = swing_table(df, cfg, ev)
    view = df.iloc[-bars:]
    d = view.index
    start = d[0]
    tab = tab_full[tab_full.date >= start]
    print(f"\n{'=' * 78}\nSWING POINTS on {symbol} {tf}, last {bars} bars "
          f"({d[0].date()} to {d[-1].date()})\n{'=' * 78}")

    print("\nSTEP 1  Short-term swings (3-bar rule)")
    print("  A bar is an STH if its high is ABOVE the bar before AND the bar after.")
    print("  You only KNOW it the day after, when the next bar has closed lower.\n")
    for side, label in (("high", "STH"), ("low", "STL")):
        px = df[side].to_numpy()
        D = df.index
        for r in ev[(ev.side == side) & (ev.level == 1) & (ev.date >= start)].itertuples():
            i = r.bar
            word = "above" if side == "high" else "below"
            print(f"  {label} {D[i].date()}  {side} {_fmt(px[i])} is {word} "
                  f"{_fmt(px[i-1])} ({D[i-1].date()}) and {_fmt(px[i+1])} ({D[i+1].date()})"
                  f"  -> confirmed {r.confirm_date.date()}")

    print("\nSTEP 2  Promote: compare each swing with its NEIGHBOURING SWINGS (not bars)")
    for side, (l1, l2, l3) in (("high", ("STH", "ITH", "LTH")), ("low", ("STL", "ITL", "LTL"))):
        word = "higher" if side == "high" else "lower"
        for lvl, (lo, hi) in ((2, (l1, l2)), (3, (l2, l3))):
            seq = ev[(ev.side == side) & (ev.level == lvl - 1)].sort_values("bar").reset_index(drop=True)
            promoted = set(ev[(ev.side == side) & (ev.level == lvl)].bar)
            for k in range(1, len(seq) - 1):
                if seq.bar[k] in promoted and seq.date[k] >= start:
                    p, c, n = seq.iloc[k - 1], seq.iloc[k], seq.iloc[k + 1]
                    conf = ev[(ev.bar == c.bar) & (ev.side == side) & (ev.level == lvl)].confirm_date.iloc[0]
                    print(f"  {hi} {c.date.date()} {_fmt(c.price)} is {word} than {lo}s either side: "
                          f"{_fmt(p.price)} ({p.date.date()}) and {_fmt(n.price)} ({n.date.date()})"
                          f"  -> known only on {conf.date()}")
        if not len(ev[(ev.side == side) & (ev.level >= 2) & (ev.date >= start)]):
            print(f"  (no {l2}/{l3} in this window: try --bars 120)")

    print("\nSTEP 3  Open float: which swings has price NOT traded through yet?")
    last = view["close"].iloc[-1]
    print(f"  Last close {_fmt(last)} on {d[-1].date()}")
    print("  (whole history, nearest 5 above and 5 below)")
    openf = tab_full[tab_full.unbroken]
    above = openf[openf.price > last].nsmallest(5, "price")
    below = openf[openf.price <= last].nlargest(5, "price")
    for r in pd.concat([above.iloc[::-1], below]).itertuples():
        where = "ABOVE price, buy-side liquidity" if r.price > last else "BELOW price, sell-side liquidity"
        print(f"    {r.type:<3} {r.date.date()} {_fmt(r.price):>12}   {where}")

    print("\nCHECK YOURSELF")
    print("  1. Mark the STHs/STLs on TradingView first, then compare with the list above.")
    print("  2. Why can an ITH not be known on the day it prints? (Answer: it needs the NEXT STH.)")
    print("  3. Which open level would you expect price to draw to next, and why?")

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    tab.drop(columns="bar").to_csv(out / "learn_swings.csv", index=False)
    _plot(view, tab[tab.unbroken | (tab.date >= start)], f"{symbol} {tf}: swing points, last {bars} bars", out / "learn_swings.png")
    print(f"\nSaved reports/learn_swings.csv and reports/learn_swings.png")


def _plot(view, tab, title, path):
    fig, ax = plt.subplots(figsize=(14, 6.5))
    for i, (dt, r) in enumerate(view.iterrows()):
        c = "#27ae60" if r.close >= r.open else "#c0392b"
        ax.vlines(i, r.low, r.high, color=c, lw=1)
        ax.vlines(i, min(r.open, r.close), max(r.open, r.close), color=c, lw=5)
    pos = {dt: i for i, dt in enumerate(view.index)}
    span = view["high"].max() - view["low"].min()
    for r in tab.itertuples():
        i = pos[r.date]
        up = r.side == "high"
        y = r.price + (0.03 if up else -0.03) * span
        color = {1: "#7f8c8d", 2: "#2980b9", 3: "#8e44ad"}[r.level]
        ax.annotate(f"{r.type}\n{r.price:,.0f}", (i, r.price), (i, y), ha="center",
                    va="bottom" if up else "top", fontsize=7, color=color, weight="bold" if r.level > 1 else None,
                    arrowprops=dict(arrowstyle="-", color=color, lw=0.6))
        if r.unbroken:
            ax.hlines(r.price, i, len(view) - 1, colors=color, linestyles=":", lw=0.8)
    ax.set_xticks(range(0, len(view), max(1, len(view) // 10)))
    ax.set_xticklabels([view.index[i].strftime("%d %b") for i in range(0, len(view), max(1, len(view) // 10))])
    ax.set_title(title + "   (grey = short-term, blue = intermediate, purple = long-term, dotted = open float)")
    ax.margins(y=0.12)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("concept", nargs="?")
    ap.add_argument("--symbol", default="NIFTY")
    ap.add_argument("--tf", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--bars", type=int, default=30)
    a = ap.parse_args()
    if a.concept not in CONCEPTS:
        print("Concepts you can learn now:")
        for k, v in CONCEPTS.items():
            print(f"  {k:<10} {v}")
        print("Coming as modules are built: " + ", ".join(PLANNED))
        print("Full explanations: docs/CONCEPTS.md")
        return
    cfg = load_config()
    df = load(a.symbol, cfg)
    if a.tf == "weekly":
        df = to_weekly(df, cfg["data"]["weekly_rule"])
    learn_swings(df, cfg, a.symbol, a.tf, a.bars)


if __name__ == "__main__":
    main()
