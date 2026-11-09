"""Mark every ICT concept on real 15-minute data and save annotated images.

Usage:
    python -m scripts.annotate_chart CNX500_15m            # reads data/raw/CNX500_15m.csv
    python -m scripts.annotate_chart NIFTY_15m --name NIFTY

Writes reports/<name>/00_summary.png ... 04_setups.png and setups.csv.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from ict_engine.analysis.practice import analyse
from ict_engine.config import ROOT, load_config
from ict_engine.data.loader import load_csv
from ict_engine.viz.mpl import C, Ax, plt

LVL_COL = {1: C["grey"], 2: C["blue"], 3: C["purple"]}


def fmt(x):
    return f"{x:,.0f}"


def win(df, i0, i1):
    i0, i1 = max(0, int(i0)), min(len(df), int(i1))
    return df.iloc[i0:i1], i0


def footer(fig, name, res):
    m = res.m15
    fig.text(0.01, 0.004, f"{name} 15-minute · {m.index[0]:%d %b %Y} → {m.index[-1]:%d %b %Y %H:%M} · {len(m)} bars · "
             "ICT Swing Engine (github.com/RakeshDoreswamy/ict-swing-engine) · Education only, not financial advice.",
             fontsize=8, color=C["grey"])


# ------------------------------------------------------------------ 01 HTF map (daily)
def htf_map(res, name, out):
    d, sw = res.daily, res.swd
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(20, 15), gridspec_kw={"hspace": 0.18})
    A = Ax(a1, d, f"{name} DAILY · Structure and liquidity  (swing points · open float · IPDA ranges · previous week)", "%d %b")
    last = d.close.iloc[-1]
    for r in sw.itertuples():
        hi = r.side == "high"
        if r.level == 1:
            A.tri(r.bar, r.price * (1.0015 if hi else 0.9985), C["dn"] if hi else C["up"], not hi)
        else:
            A.mark(r.bar, r.price, r.type, LVL_COL[r.level], above=hi, dy=0.03)
        if r.unbroken:
            col = C["dn"] if r.price > last else C["up"]
            A.hline(r.price, r.bar, None, col, f"open {r.type} {fmt(r.price)}  ({'buy' if r.price > last else 'sell'}-side liquidity)", lw=1.1)
        elif r.level >= 2:
            j = d.index.get_loc(r.broken_date)
            A.hline(r.price, r.bar, j, LVL_COL[r.level], None, lw=0.8)
            A.ax.scatter([j], [r.price], marker="x", color=LVL_COL[r.level], s=30, zorder=7)
    cols = {20: C["teal"], 40: C["gold"], 60: C["purple"]}
    n = len(d)
    for k, v in res.ipda.items():
        A.hline(v["high"], n - k, None, cols[k], None, ls="-", lw=0.9)
        A.hline(v["low"], n - k, None, cols[k], None, ls="-", lw=0.9)
        A.ax.text(n - k, v["high"], f" IPDA {k}d high {fmt(v['high'])}", color=cols[k], fontsize=7.5, va="bottom", fontweight="bold")
        A.ax.text(n - k, v["low"], f" IPDA {k}d low {fmt(v['low'])}", color=cols[k], fontsize=7.5, va="top", fontweight="bold")
    pw = res.weekly.iloc[-2]
    A.hline(pw.high, n - 6, None, C["gold"], f"prev week high {fmt(pw.high)}", ls="-", lw=1.6)
    A.hline(pw.low, n - 6, None, C["gold"], f"prev week low {fmt(pw.low)}", ls="-", lw=1.6)
    for q in res.qshift.itertuples():
        A.shade(q.bar, "#e9dcff", 0.8)
        A.mark(q.bar, d.high.iloc[q.bar] if q.direction == "up" else d.low.iloc[q.bar],
               f"shift {q.direction}: close through 40-day range", C["purple"], above=q.direction == "up", dy=0.06)
    A.note("BIAS (step 1): " + res.bias["sentence"] + "\n▲▼ short-term swings · blue = intermediate · purple = long-term · "
           "✕ = level taken · lines to right edge = open float", loc=(0.01, 0.16), fs=9)

    B = Ax(a2, d, f"{name} DAILY · PD arrays and premium/discount  (FVG · order blocks · dealing range · OTE)", "%d %b")
    for g in res.fvgd.itertuples():
        open_ = pd.isna(g.filled_bar)
        end = None if open_ else int(g.filled_bar)
        col = C["bull"] if g.side == "bull" else C["bear"]
        B.zone(g.bar, end, g.top, g.bottom, col, f"{g.side} FVG {'OPEN' if open_ else 'filled'}" if open_ else None,
               alpha=0.22 if open_ else 0.08)
        if open_:
            B.hline(g.ce, g.bar, None, col, f"CE {fmt(g.ce)}", ls=":", lw=0.8)
    obs = res.obd[res.obd.breaker_bar.isna()].tail(4)
    for o in obs.itertuples():
        col = C["blue"] if o.side == "bull" else C["purple"]
        B.zone(o.bar, None, o.top, o.bottom, col, f"{o.side} order block (unbroken)", alpha=0.12)
    rng = res.range_d
    if rng:
        i0 = min(rng["high_bar"], rng["low_bar"])
        B.zone(i0, None, rng["high"], rng["eq"], C["bear"], None, alpha=0.06, edge=False)
        B.zone(i0, None, rng["eq"], rng["low"], C["bull"], None, alpha=0.06, edge=False)
        B.hline(rng["eq"], i0, None, C["blue"], f"EQUILIBRIUM {fmt(rng['eq'])}", ls="-", lw=1.3)
        lo_, hi_ = sorted([rng["ote_62"], rng["ote_79"]])
        B.zone(i0, None, hi_, lo_, C["gold"], None, alpha=0.18)
        B.hline(rng["ote_705"], i0, None, C["gold"], f"OTE 62–79% ({fmt(lo_)}–{fmt(hi_)}), 70.5% = {fmt(rng['ote_705'])}", ls=":", lw=1)
        B.mark(rng["high_bar"], rng["high"], f"range high {fmt(rng['high'])}", C["dn"], dy=0.04)
        B.mark(rng["low_bar"], rng["low"], f"range low {fmt(rng['low'])}", C["up"], above=False, dy=0.04)
        B.rtext(rng["high"] - (rng["high"] - rng["eq"]) * 0.2, "PREMIUM (sell zone)", C["bear"], 9.5)
        B.rtext(rng["low"] + (rng["eq"] - rng["low"]) * 0.1, "DISCOUNT (buy zone)", C["bull"], 9.5)
    footer(fig, name, res)
    fig.savefig(out / "01_htf_map_daily.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ 02 live 15m view
def live_view(res, name, out, sessions=5):
    m = res.m15
    n = sessions * 25
    df, off = win(m, len(m) - n, len(m))
    fig, ax = plt.subplots(figsize=(24, 12))
    A = Ax(ax, df, f"{name} 15-MINUTE · last {sessions} sessions · every concept marked", "%d %b %H:%M", nticks=12)
    A.day_separators()
    # displacement
    for i, v in enumerate(res.disp15.iloc[off:].values):
        if v:
            A.shade(i, "#f3e3c3", 0.75)
    # previous day high/low
    days = df.index.normalize()
    ud = list(dict.fromkeys(days))
    allday = m.index.normalize()
    for dd in ud:
        idx = np.nonzero(days == dd)[0]
        prev_days = sorted(set(allday[allday < dd]))
        if not prev_days:
            continue
        pdf = m[allday == prev_days[-1]]
        A.hline(pdf.high.max(), idx[0], idx[-1], C["gold"], None, ls="-", lw=1.4)
        A.hline(pdf.low.min(), idx[0], idx[-1], C["gold"], None, ls="-", lw=1.4)
    # FVGs
    g = res.fvg15[(res.fvg15.bar >= off)]
    for r in g.itertuples():
        open_ = pd.isna(r.filled_bar)
        end = None if open_ else int(r.filled_bar) - off
        col = C["bull"] if r.side == "bull" else C["bear"]
        A.zone(r.bar - off, end, r.top, r.bottom, col, None, alpha=0.22 if open_ else 0.10)
        if open_:
            A.hline(r.ce, r.bar - off, None, col, f"open {r.side} FVG · CE {fmt(r.ce)}", ls=":", lw=0.8)
    # order blocks / breakers
    for o in res.ob15[res.ob15.bar >= off].itertuples():
        col = C["blue"] if o.side == "bull" else C["purple"]
        if pd.isna(o.breaker_bar):
            A.zone(o.bar - off, min(o.bar - off + 12, len(df) - 1), o.top, o.bottom, col, f"{o.side} OB", alpha=0.13, fs=7)
        else:
            bb = int(o.breaker_bar) - off
            A.zone(o.bar - off, bb, o.top, o.bottom, col, None, alpha=0.10)
            if bb < len(df):
                A.zone(bb, min(bb + 15, len(df) - 1), o.top, o.bottom, C["dn"] if o.side == "bull" else C["up"],
                       "breaker", alpha=0.15, fs=7, where="left")
    # swings
    sw = res.sw15[res.sw15.bar >= off]
    for r in sw.itertuples():
        hi = r.side == "high"
        i = r.bar - off
        if r.level == 1:
            A.tri(i, r.price, C["dn"] if hi else C["up"], not hi)
        else:
            A.mark(i, r.price, r.type, LVL_COL[r.level], above=hi, dy=0.025, fs=7)
    # liquidity pools: equal highs/lows among swings INSIDE this window that are still untouched
    from ict_engine.detectors.basic import equal_levels
    tol = 0.25 * float(res.atr15.median())
    last = m.close.iloc[-1]
    pools = []
    for p in equal_levels(sw, tol):
        after = m.iloc[max(p["bars"]) + 1:]
        ok = (after.high <= p["price"]).all() if p["side"] == "high" else (after.low >= p["price"]).all()
        if ok:
            pools.append(p)
    up = sorted([p for p in pools if p["side"] == "high" and p["price"] > last], key=lambda p: p["price"])[:3]
    dn = sorted([p for p in pools if p["side"] == "low" and p["price"] < last], key=lambda p: -p["price"])[:3]
    for p in up + dn:
        col = C["dn"] if p["side"] == "high" else C["up"]
        A.hline(p["price"], min(p["bars"]) - off, None, col,
                f"{'BSL' if p['side'] == 'high' else 'SSL'} pool: equal {'highs' if p['side'] == 'high' else 'lows'} ×{p['touches']} {fmt(p['price'])}", ls="--", lw=1.2)
        for b in p["bars"]:
            A.ax.scatter([b - off], [p["price"]], marker="_", s=90, color=col, zorder=7, lw=2)
    # sweeps & MSS
    for s in res.sweeps15[(res.sweeps15.bar >= off) & res.sweeps15.swing_type.isin(["ITH", "ITL", "LTH", "LTL"])].itertuples():
        lo = s.side == "sell-side"
        A.mark(s.bar - off, m.low.iloc[s.bar] if lo else m.high.iloc[s.bar], f"{'SSL' if lo else 'BSL'} sweep", C["teal"], above=not lo, dy=0.05, fs=7, marker="D")
    for x in res.mss15[res.mss15.bar >= off].itertuples():
        bull = x.side == "bull"
        A.hline(x.level, max(x.swing_bar - off, 0), x.bar - off, C["blue"], None, ls="-", lw=1.3)
        A.mark(x.bar - off, m.high.iloc[x.bar] if bull else m.low.iloc[x.bar], f"MSS {'↑' if bull else '↓'}", C["blue"], above=bull, dy=0.07, fs=7.5, marker="*")
    # dealing range
    rng = res.range15
    if rng and min(rng["high_bar"], rng["low_bar"]) >= off:
        i0 = min(rng["high_bar"], rng["low_bar"]) - off
        A.hline(rng["eq"], i0, None, C["blue"], f"15m EQ {fmt(rng['eq'])}", ls="-", lw=1.2)
        lo_, hi_ = sorted([rng["ote_62"], rng["ote_79"]])
        A.zone(i0, None, hi_, lo_, C["gold"], None, alpha=0.18)
        A.rtext(hi_, f"15m OTE {fmt(lo_)}–{fmt(hi_)}", C["gold"], 7.5)
    A.note("LEGEND  ▲▼ short-term swing · blue ITH/ITL · purple LTH/LTL · gold lines = previous day high/low · shaded candle = displacement\n"
           "green/red box = bullish/bearish FVG (dotted = CE of open FVG) · blue/purple box = bull/bear order block · breaker = failed OB flipped\n"
           "dashed = untouched equal highs (BSL pool) / equal lows (SSL pool) · ◆ = sweep of intermediate/long-term liquidity · ★ = market structure shift by close", fs=8.5)
    footer(fig, name, res)
    fig.savefig(out / "02_live_15m_all_concepts.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ 03 concept atlas
def atlas(res, name, out):
    m, sw = res.m15, res.sw15
    N = len(m)
    fig, axes = plt.subplots(4, 3, figsize=(27, 30), gridspec_kw={"hspace": 0.42, "wspace": 0.16})
    axes = axes.ravel()
    good = res.setups[res.setups.result == "target"]
    ex = good.iloc[-1] if len(good) else res.setups.iloc[-1]

    def cap(ax, text):
        ax.text(0, -0.13, text, transform=ax.transAxes, fontsize=9.2, va="top", ha="left", wrap=True, color=C["ink"])

    # 1 swing points
    df, off = win(m, N - 40, N)
    A = Ax(axes[0], df, "1 · Swing points (STH / STL)", "%d %b %H:%M", 6)
    s1 = sw[(sw.bar >= off)]
    for r in s1.itertuples():
        hi = r.side == "high"
        A.mark(r.bar - off, r.price, "STH" if hi else "STL", C["dn"] if hi else C["up"], above=hi, dy=0.04, fs=7, box=False)
    last_h = s1[s1.side == "high"].iloc[-1]
    A.shade(last_h.bar - off)
    A.shade(last_h.bar - off + 1, "#cfe0ff", 0.6)
    cap(axes[0], f"Every 3-bar high/low in the last 40 bars. Shaded example: STH {fmt(last_h.price)} at {last_h.date:%d %b %H:%M} (orange) is only\n"
                 f"CONFIRMED when the next bar (blue) closes lower. {len(s1)} swings in this window, {len(sw)} in 90 days.")

    # 2 institutional swings
    df, off = win(m, N - 250, N)
    A = Ax(axes[1], df, "2 · Institutional swings (ITH / LTH / ITL / LTL)", "%d %b", 6)
    A.day_separators()
    s2 = sw[(sw.bar >= off) & (sw.level >= 2)]
    for r in s2.itertuples():
        A.mark(r.bar - off, r.price, r.type, LVL_COL[r.level], above=r.side == "high", dy=0.03, fs=7)
    cap(axes[1], f"Last 10 sessions. Only intermediate (blue) and long-term (purple) swings are labelled: {len(s2)} of "
                 f"{len(sw[sw.bar >= off])} swings.\nAn ITH is an STH with lower STHs either side; an LTH is an ITH with lower ITHs either side.")

    # 3 open float
    df, off = win(m, N - 300, N)
    A = Ax(axes[2], df, "3 · Open float (untouched highs and lows)", "%d %b", 6)
    last = m.close.iloc[-1]
    s3 = sw[(sw.bar >= off) & (sw.level >= 2)]
    n_open = 0
    for r in s3.itertuples():
        if r.unbroken:
            n_open += 1
            col = C["dn"] if r.price > last else C["up"]
            A.hline(r.price, r.bar - off, None, col, f"{r.type} {fmt(r.price)} OPEN", lw=1.2, fs=7)
        else:
            j = m.index.get_loc(r.broken_date) - off
            A.hline(r.price, r.bar - off, j, C["grey"], None, lw=0.7)
            A.ax.scatter([j], [r.price], marker="x", color=C["grey"], s=20, zorder=7)
    cap(axes[2], f"Intermediate/long-term swings of the last 12 sessions. Grey lines end with ✕ where price took the level.\n"
                 f"{n_open} are still OPEN (run to the right edge): red above price = buy-side liquidity, green below = sell-side liquidity.")

    # 4 liquidity pool (equal highs/lows that were later taken)
    taken = [p for p in res.pools15 if p["taken_bar"] is not None and p["touches"] >= 2 and p["taken_bar"] - min(p["bars"]) < 60]
    p = max(taken[-40:], key=lambda q: (q["touches"], q["taken_bar"])) if taken else res.pools15[-1]
    df, off = win(m, min(p["bars"]) - 12, (p["taken_bar"] or max(p["bars"])) + 15)
    A = Ax(axes[3], df, "4 · Liquidity pool (equal highs / equal lows)", "%d %b %H:%M", 6)
    col = C["dn"] if p["side"] == "high" else C["up"]
    tb = p["taken_bar"] - off if p["taken_bar"] is not None else None
    A.hline(p["price"], min(p["bars"]) - off, tb, col, f"equal {'highs' if p['side'] == 'high' else 'lows'} {fmt(p['price'])}", lw=1.4)
    for b in p["bars"]:
        A.mark(b - off, p["price"], "=", col, above=p["side"] == "high", dy=0.03, fs=8, box=False)
    if tb is not None:
        A.shade(tb)
        A.mark(tb, m.high.iloc[p["taken_bar"]] if p["side"] == "high" else m.low.iloc[p["taken_bar"]], "pool taken", C["teal"], above=p["side"] == "high", dy=0.06)
    cap(axes[3], f"{p['touches']} swing {'highs' if p['side'] == 'high' else 'lows'} within {0.25 * float(res.atr15.median()):,.0f} points of {fmt(p['price'])}: "
                 f"stops cluster {'above' if p['side'] == 'high' else 'below'} them.\n"
                 + (f"Price ran through the pool at {m.index[p['taken_bar']]:%d %b %H:%M}." if tb is not None else "Still open."))

    # 5 sweep (from the example setup)
    sb = int(ex.sweep_bar)
    df, off = win(m, sb - 25, sb + 20)
    A = Ax(axes[4], df, "5 · Liquidity sweep (stop hunt)", "%d %b %H:%M", 6)
    lo = ex.side == "long"
    lvl_row = sw[(sw.price == ex.sweep_level)]
    i_sw = int(lvl_row.bar.iloc[0]) - off if len(lvl_row) else 0
    A.hline(ex.sweep_level, max(i_sw, 0), sb - off, C["up"] if lo else C["dn"], f"{ex.sweep_type} {fmt(ex.sweep_level)}", lw=1.3)
    A.shade(sb - off)
    ext = m.low.iloc[sb] if lo else m.high.iloc[sb]
    A.mark(sb - off, ext, f"wick to {fmt(ext)} takes the stops", C["teal"], above=not lo, dy=0.07)
    A.mark(sb - off, m.close.iloc[sb], f"close {fmt(m.close.iloc[sb])} back inside", C["blue"], above=lo, dy=0.10)
    cap(axes[5 - 1], f"{m.index[sb]:%d %b %H:%M}: the candle traded {'below' if lo else 'above'} the {ex.sweep_type} at {fmt(ex.sweep_level)} "
                     f"but CLOSED back {'above' if lo else 'below'} it.\nThat is a {'sell' if lo else 'buy'}-side sweep. Liquidity taken, reversal likely.")

    # 6 displacement
    df, off = win(m, N - 75, N)
    A = Ax(axes[5], df, "6 · Displacement candles", "%d %b %H:%M", 6)
    body = (m.close - m.open).abs()
    ratio = body / res.atr15.shift(1)
    dsp = [i for i, v in enumerate(res.disp15.iloc[off:].values) if v]
    for i in dsp:
        A.shade(i)
    if dsp:
        big = max(dsp, key=lambda i: body.iloc[off + i])
        A.mark(big, m.high.iloc[off + big] if m.close.iloc[off + big] > m.open.iloc[off + big] else m.low.iloc[off + big],
               f"body = {ratio.iloc[off + big]:.1f} × ATR", C["gold"], above=m.close.iloc[off + big] > m.open.iloc[off + big], dy=0.06)
    cap(axes[5], f"Last 3 sessions: {len(dsp)} candles (shaded) have a body larger than 1.2 × ATR(14).\n"
                 "These are the moves that create FVGs, define order blocks and confirm MSS.")

    # 7 FVG (from example)
    gb = int(ex.fvg_bar)
    gr = res.fvg15[res.fvg15.bar == gb].iloc[0]
    df, off = win(m, gb - 12, gb + 30)
    A = Ax(axes[6], df, "7 · Fair value gap (FVG) + CE", "%d %b %H:%M", 6)
    end = int(gr.filled_bar) - off if pd.notna(gr.filled_bar) else None
    colf = C["bull"] if gr.side == "bull" else C["bear"]
    A.zone(gb - off - 1, end, gr.top, gr.bottom, colf, f"{gr.side} FVG {fmt(gr.bottom)}–{fmt(gr.top)}", alpha=0.25)
    A.hline(gr.ce, gb - off - 1, end, C["blue"], f"CE {fmt(gr.ce)}", ls=":")
    for k, t in ((-1, "1"), (0, "2"), (1, "3")):
        A.mark(gb - off + k, m.high.iloc[gb + k], f"c{t}", C["grey"], dy=0.03, fs=7, box=False)
    ft = gr.first_touch_bar
    if pd.notna(ft) and int(ft) - off < len(df):
        A.shade(int(ft) - off, "#cfe0ff", 0.7)
    cap(axes[6], f"Candle 1's {'high' if gr.side == 'bull' else 'low'} and candle 3's {'low' if gr.side == 'bull' else 'high'} do not overlap: a {gr.side} FVG "
                 f"of {gr.size:,.1f} points ({m.index[gb]:%d %b %H:%M}).\n"
                 + (f"Price came back into it at {m.index[int(ft)]:%H:%M} (blue). " if pd.notna(ft) else "")
                 + ("Fully filled later." if pd.notna(gr.filled_bar) else "Not fully filled."))

    # 8 order block respected
    obs = res.ob15[res.ob15.bar < N - 30]
    pick = None
    for o in obs.iloc[::-1].itertuples():
        j = o.displacement_bar
        later = m.iloc[j + 1: j + 31]
        touched = (later.low <= o.top).any() if o.side == "bull" else (later.high >= o.bottom).any()
        held = pd.isna(o.breaker_bar) or o.breaker_bar > j + 30
        if touched and held:
            pick = o
            break
    pick = pick or obs.iloc[-1]
    df, off = win(m, pick.bar - 10, pick.displacement_bar + 32)
    A = Ax(axes[7], df, "8 · Order block (and mean threshold)", "%d %b %H:%M", 6)
    colo = C["blue"] if pick.side == "bull" else C["purple"]
    A.zone(pick.bar - off, None, pick.top, pick.bottom, colo, f"{pick.side} OB {fmt(pick.bottom)}–{fmt(pick.top)}", alpha=0.2)
    A.hline(pick.mean, pick.bar - off, None, colo, f"mean {fmt(pick.mean)}", ls=":")
    A.shade(pick.displacement_bar - off)
    A.mark(pick.bar - off, pick.bottom if pick.side == "bull" else pick.top, "last opposite candle", colo, above=pick.side != "bull", dy=0.06)
    cap(axes[7], f"{pick.date:%d %b %H:%M}: the last {'down' if pick.side == 'bull' else 'up'}-close candle before a displacement candle (shaded) = {pick.side} order block.\n"
                 "Price returned into the block within 30 bars and the block was not closed through. The OB held.")

    # 9 breaker
    brk = res.ob15[res.ob15.breaker_bar.notna() & (res.ob15.breaker_bar < N - 15)]
    pick = None
    for o in brk.iloc[::-1].itertuples():
        bb = int(o.breaker_bar)
        later = m.iloc[bb + 1: bb + 21]
        if (o.side == "bull" and (later.high >= o.bottom).any()) or (o.side == "bear" and (later.low <= o.top).any()):
            pick = o
            break
    pick = pick or brk.iloc[-1]
    bb = int(pick.breaker_bar)
    df, off = win(m, pick.bar - 8, bb + 22)
    A = Ax(axes[8], df, "9 · Breaker block (failed OB flips sides)", "%d %b %H:%M", 6)
    c1 = C["blue"] if pick.side == "bull" else C["purple"]
    c2 = C["dn"] if pick.side == "bull" else C["up"]
    A.zone(pick.bar - off, bb - off, pick.top, pick.bottom, c1, f"{pick.side} OB", alpha=0.18)
    A.zone(bb - off, None, pick.top, pick.bottom, c2, f"now {'bearish' if pick.side == 'bull' else 'bullish'} breaker", alpha=0.18, where="left")
    A.shade(bb - off)
    cap(axes[8], f"The {pick.side} order block from {pick.date:%d %b %H:%M} was CLOSED through at {m.index[bb]:%d %b %H:%M} (shaded).\n"
                 f"Afterwards price came back to the zone from the other side, where it now acts as {'resistance' if pick.side == 'bull' else 'support'}.")

    # 10 premium/discount + 11 OTE: use an intermediate up leg followed by a retracement into OTE
    swi = sw[sw.level >= 2].sort_values("bar")
    leg = None
    for k in range(len(swi) - 1, 0, -1):
        a, b = swi.iloc[k - 1], swi.iloc[k]
        if a.side == "low" and b.side == "high" and b.bar < N - 20:
            rngv = b.price - a.price
            o62, o79 = b.price - 0.62 * rngv, b.price - 0.79 * rngv
            later = m.iloc[b.bar + 1: b.bar + 41]
            # a clean OTE example: pullback reaches the 62% line but holds above ~85% of the leg,
            # and price later trades back above the pullback's start (continuation)
            if len(later) and o79 - 0.06 * rngv <= later.low.min() <= o62 and later.high.iloc[-10:].max() > o62 and rngv > 2 * float(res.atr15.iloc[b.bar]):
                leg = (a, b, o62, o79)
                break
    if leg is None:
        a, b = swi[swi.side == "low"].iloc[-1], swi[swi.side == "high"].iloc[-1]
        rngv = b.price - a.price
        leg = (a, b, b.price - 0.62 * rngv, b.price - 0.79 * rngv)
    a, b, o62, o79 = leg
    eq = (a.price + b.price) / 2
    for idx, (title, show_ote) in enumerate((("10 · Premium / discount / equilibrium", False), ("11 · OTE: optimal trade entry (62–79%)", True))):
        df, off = win(m, a.bar - 8, b.bar + 42)
        A = Ax(axes[9 + idx], df, title, "%d %b %H:%M", 6)
        A.zone(a.bar - off, None, b.price, eq, C["bear"], "PREMIUM (sell)" if not show_ote else None, alpha=0.08)
        A.zone(a.bar - off, None, eq, a.price, C["bull"], "DISCOUNT (buy)" if not show_ote else None, alpha=0.08, where="left")
        A.hline(eq, a.bar - off, None, C["blue"], f"EQ 50% {fmt(eq)}", ls="-")
        A.mark(a.bar - off, a.price, f"{a.type} {fmt(a.price)}", C["up"], above=False, dy=0.04)
        A.mark(b.bar - off, b.price, f"{b.type} {fmt(b.price)}", C["dn"], dy=0.04)
        if show_ote:
            A.zone(b.bar - off, None, o62, o79, C["gold"], "OTE 62–79%", alpha=0.25)
            A.hline(b.price - 0.705 * (b.price - a.price), b.bar - off, None, C["gold"], f"70.5% {fmt(b.price - 0.705 * (b.price - a.price))}", ls=":")
        later = m.iloc[b.bar + 1: b.bar + 41]
        lowest = later.low.idxmin()
        A.mark(m.index.get_loc(lowest) - off, later.low.min(), f"pullback low {fmt(later.low.min())}", C["teal"], above=False, dy=0.06)
    cap(axes[9], f"Dealing range = {a.type} {fmt(a.price)} → {b.type} {fmt(b.price)}. Above {fmt(eq)} is premium (sell only),\n"
                 "below is discount (buy only). The pullback after the high reached discount: the buy side of the range.")
    cap(axes[10], f"OTE band of the same leg: {fmt(o79)}–{fmt(o62)}. The pullback low {fmt(m.iloc[b.bar + 1: b.bar + 41].low.min())} reached it.\n"
                  "Entering there keeps the stop (below the leg low) close and the target (leg high and beyond) far.")

    # 12 MSS (from example)
    mb = int(ex.mss_bar)
    df, off = win(m, int(ex.sweep_bar) - 15, mb + 18)
    A = Ax(axes[11], df, "12 · Market structure shift (MSS)", "%d %b %H:%M", 6)
    bull = ex.side == "long"
    msr = res.mss15[res.mss15.bar == mb].iloc[0]
    A.hline(ex.mss_level, max(int(msr.swing_bar) - off, 0), mb - off, C["blue"], f"last {'STH' if bull else 'STL'} {fmt(ex.mss_level)}", lw=1.4)
    A.shade(mb - off)
    A.mark(mb - off, m.close.iloc[mb], f"CLOSE {fmt(m.close.iloc[mb])} {'above' if bull else 'below'} it", C["blue"], above=bull, dy=0.08, marker="*")
    A.mark(int(ex.sweep_bar) - off, m.low.iloc[int(ex.sweep_bar)] if bull else m.high.iloc[int(ex.sweep_bar)], "sweep first", C["teal"], above=not bull, dy=0.06, marker="D")
    cap(axes[11], f"After the sweep, the candle at {m.index[mb]:%d %b %H:%M} CLOSED {'above' if bull else 'below'} the last short-term "
                  f"{'high' if bull else 'low'} ({fmt(ex.mss_level)}) with displacement.\nShort-term structure flipped {'up' if bull else 'down'}. This is the trigger.")
    fig.subplots_adjust(top=0.965, bottom=0.075)
    fig.suptitle(f"{name} · ICT concept atlas: 12 concepts found automatically in 90 days of 15-minute data", fontsize=16, fontweight="bold", x=0.01, ha="left", y=0.995)
    footer(fig, name, res)
    fig.savefig(out / "03_concept_atlas.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ 04 setups
def setups(res, name, out, k=6):
    m, S = res.m15, res.setups
    traded = S[S.R.notna()]
    show = traded[traded.grade == "A"].tail(k)
    if len(show) < k:
        show = traded.tail(k)
    rows = int(np.ceil(len(show) / 2))
    fig = plt.figure(figsize=(26, 9 * rows + 7))
    gs = fig.add_gridspec(rows + 1, 2, height_ratios=[9] * rows + [4.6], hspace=0.38, wspace=0.12)
    for n, t in enumerate(show.itertuples()):
        ax = fig.add_subplot(gs[n // 2, n % 2])
        i0, i1 = t.sweep_bar - 14, (t.exit_bar if t.exit_bar is not None and not pd.isna(t.exit_bar) else t.mss_bar + 20) + 8
        df, off = win(m, i0, i1)
        bull = t.side == "long"
        A = Ax(ax, df, f"SETUP {t.Index + 1} · {t.side.upper()} · {t.mss_time:%d %b %Y} · grade {t.grade} · result {t.result.upper()} ({t.R:+.2f}R)", "%d %b %H:%M", 7)
        A.day_separators()
        A.mark(t.sweep_bar - off, m.low.iloc[t.sweep_bar] if bull else m.high.iloc[t.sweep_bar], f"① {t.sweep_type} sweep", C["teal"], above=not bull, dy=0.06, marker="D")
        A.shade(t.mss_bar - off)
        A.mark(t.mss_bar - off, m.high.iloc[t.mss_bar] if bull else m.low.iloc[t.mss_bar], "② MSS by close", C["blue"], above=bull, dy=0.07, marker="*")
        A.hline(t.mss_level, max(t.mss_bar - off - 8, 0), t.mss_bar - off, C["blue"], None, ls="-", lw=1.2)
        A.zone(t.fvg_bar - off - 1, None, t.fvg_top, t.fvg_bottom, C["bull"] if bull else C["bear"], "③ FVG", alpha=0.22)
        x0 = t.fill_bar - off if pd.notna(t.fill_bar) else t.fvg_bar - off
        risk = abs(t.entry - t.stop)
        A.hline(t.entry, x0, None, C["blue"], f"④ entry (limit at CE) {fmt(t.entry)}", ls="-", lw=1.4)
        A.hline(t.stop, x0, None, C["dn"], f"⑤ stop {fmt(t.stop)}  (risk {risk:,.1f} pts = 1R)", ls="-", lw=1.4)
        A.hline(t.target, x0, None, C["up"], f"⑥ target {fmt(t.target)}  (R:R {t.rr:.2f})", ls="-", lw=1.4)
        A.zone(x0, None, max(t.entry, t.target), min(t.entry, t.target), C["up"], None, alpha=0.06, edge=False)
        A.zone(x0, None, max(t.entry, t.stop), min(t.entry, t.stop), C["dn"], None, alpha=0.06, edge=False)
        one_r = t.entry + risk if bull else t.entry - risk
        A.hline(one_r, x0, None, C["purple"], f"+1R {fmt(one_r)} → stop to breakeven", ls=":", lw=1)
        if pd.notna(t.fill_bar):
            A.mark(t.fill_bar - off, t.entry, "filled", C["blue"], above=not bull, dy=0.05, fs=7)
        if t.exit_bar is not None and pd.notna(t.exit_bar) and t.exit_bar - off < len(df):
            colx = C["up"] if t.R > 0 else C["dn"] if t.R < 0 else C["grey"]
            A.mark(int(t.exit_bar) - off, t.exit, f"exit {t.result} {t.R:+.2f}R", colx, above=bull == (t.R > 0), dy=0.06)
        size = int(1_000_000 * 0.01 // (risk * 1.25)) if risk else 0
        A.note(f"Checklist: sweep ✔  MSS ✔  FVG ✔  {'discount' if bull else 'premium'} {'✔' if 'discount' not in t.missing else '✘'}  "
               f"R:R≥1.5 ✔  filled ✔\nSize at 1% of Rs 10L (×1.25 gap pad): {size:,} units", fs=8.3)
    # table
    ax = fig.add_subplot(gs[rows, :])
    ax.axis("off")
    tt = traded.copy()
    a_ = tt[tt.grade == "A"]
    stats = (f"ALL {len(S)} sweep→MSS→FVG setups in 90 days: {len(tt)} filled & traded · {(S.result == 'no fill').sum()} limit not filled · "
             f"{S.result.str.startswith('skipped').sum()} skipped (R:R<1.5)\n"
             f"Traded: win rate {(tt.R > 0).mean() * 100:.0f}% · average {tt.R.mean():+.2f}R · total {tt.R.sum():+.1f}R    |    "
             f"Grade A only ({len(a_)}): win rate {(a_.R > 0).mean() * 100:.0f}% · average {a_.R.mean():+.2f}R · total {a_.R.sum():+.1f}R\n"
             "Small sample on one instrument, 15-minute bars, no costs: a learning exercise, NOT evidence of an edge (need 30+ trades per rule set, out of sample).")
    ax.text(0, 1.0, stats, fontsize=11, va="top", fontweight="bold", color=C["ink"])
    last = tt.tail(14)
    cells = [[f"{r.mss_time:%d %b %H:%M}", r.side, r.sweep_type, fmt(r.entry), fmt(r.stop), fmt(r.target), f"{r.rr:.2f}", r.result, f"{r.R:+.2f}", r.grade, r.missing or "—"]
             for r in last.itertuples()]
    tb = ax.table(cellText=cells, colLabels=["MSS time", "side", "swept", "entry", "stop", "target", "R:R", "result", "R", "grade", "missing checks"],
                  loc="lower left", bbox=[0, 0, 1, 0.74], cellLoc="left")
    tb.auto_set_font_size(False)
    tb.set_fontsize(9)
    for (rr, cc), cell in tb.get_celld().items():
        cell.set_edgecolor("#e4e1da")
        if rr == 0:
            cell.set_facecolor("#f3f1ec")
            cell.set_text_props(fontweight="bold")
        elif cc == 8:
            v = float(cells[rr - 1][8])
            cell.set_text_props(color=C["up"] if v > 0 else C["dn"] if v < 0 else C["grey"], fontweight="bold")
    fig.subplots_adjust(top=0.965)
    fig.suptitle(f"{name} · complete ICT setups (bias → sweep → MSS → FVG → entry/stop/target → managed exit) on real 15-minute data",
                 fontsize=15, fontweight="bold", x=0.01, ha="left", y=0.995)
    footer(fig, name, res)
    fig.savefig(out / "04_setups_and_results.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ 00 summary
def summary(res, name, out):
    m, b = res.m15, res.bias
    last = m.close.iloc[-1]
    sw = res.sw15
    above = sw[(sw.side == "high") & sw.unbroken & (sw.price > last) & (sw.level >= 2)].nsmallest(3, "price")
    below = sw[(sw.side == "low") & sw.unbroken & (sw.price < last) & (sw.level >= 2)].nlargest(3, "price")
    of = res.fvg15[res.fvg15.filled_bar.isna()].tail(4)
    ob = res.ob15[res.ob15.breaker_bar.isna()].tail(3)
    rng, r15 = res.range_d, res.range15
    S = res.setups
    latest = S.iloc[-1]
    lines = [
        ("STEP 1 · BIAS (daily, from 15m)", b["sentence"]),
        ("DAILY DEALING RANGE", f"{fmt(rng['low'])} → {fmt(rng['high'])} · EQ {fmt(rng['eq'])} · OTE {fmt(min(rng['ote_62'], rng['ote_79']))}–{fmt(max(rng['ote_62'], rng['ote_79']))} · price is in {b['zone'].upper()}"),
        ("IPDA RANGES (daily)", " · ".join(f"{k}d {fmt(v['low'])}–{fmt(v['high'])}" for k, v in res.ipda.items())),
        ("PREVIOUS WEEK", f"high {fmt(res.weekly.iloc[-2].high)} · low {fmt(res.weekly.iloc[-2].low)}"),
        ("BUY-SIDE LIQUIDITY ABOVE (15m ITH/LTH open)", " · ".join(f"{r.type} {fmt(r.price)} ({r.date:%d %b %H:%M})" for r in above.itertuples()) or "none"),
        ("SELL-SIDE LIQUIDITY BELOW (15m ITL/LTL open)", " · ".join(f"{r.type} {fmt(r.price)} ({r.date:%d %b %H:%M})" for r in below.itertuples()) or "none"),
        ("OPEN 15m FVGs", " · ".join(f"{g.side} {fmt(g.bottom)}–{fmt(g.top)} CE {fmt(g.ce)}" for g in of.itertuples()) or "none"),
        ("UNBROKEN 15m ORDER BLOCKS", " · ".join(f"{o.side} {fmt(o.bottom)}–{fmt(o.top)} ({o.date:%d %b %H:%M})" for o in ob.itertuples()) or "none"),
        ("15m DEALING RANGE", f"{fmt(r15['low'])} → {fmt(r15['high'])} · EQ {fmt(r15['eq'])}" if r15 else "n/a"),
        ("LATEST SETUP", f"{latest.side} · MSS {latest.mss_time:%d %b %H:%M} · entry {fmt(latest.entry)} stop {fmt(latest.stop)} target "
                         f"{fmt(latest.target) if pd.notna(latest.target) else '—'} · {latest.result} · grade {latest.grade}"),
        ("90-DAY COUNTS", f"{len(sw)} swings ({(sw.level >= 2).sum()} intermediate+) · {len(res.fvg15)} FVGs · {len(res.ob15)} order blocks · "
                          f"{len(res.sweeps15)} sweeps · {len(res.mss15)} MSS · {len(S)} full setups"),
    ]
    fig = plt.figure(figsize=(20, 11))
    fig.text(0.02, 0.95, f"{name} · ICT state as of {m.index[-1]:%d %b %Y %H:%M} · last {fmt(last)}", fontsize=20, fontweight="bold", color=C["ink"])
    fig.text(0.02, 0.91, "Every value below is computed by the engine's rules from the attached 15-minute file. Nothing is drawn by hand.",
             fontsize=11, color=C["grey"])
    y = 0.85
    for t, v in lines:
        fig.text(0.02, y, t, fontsize=10.5, fontweight="bold", color=C["blue"])
        fig.text(0.02, y - 0.03, v, fontsize=11.5, color=C["ink"], wrap=True)
        y -= 0.073
    fig.text(0.02, 0.02, "Education only, not financial advice. ICT concepts are not independently proven; this engine exists to test them.", fontsize=9, color=C["grey"])
    fig.savefig(out / "00_summary.png", dpi=130, facecolor="white")
    plt.close(fig)


PAGE_IMAGES = [
    ("00_summary.png", "Current state", "Bias, dealing ranges, IPDA ranges, open liquidity above and below, open FVGs, unbroken order blocks and the latest setup, all computed from the file."),
    ("01_htf_map_daily.png", "Higher-timeframe map (daily)", "Top: structure and liquidity (swings, open float, IPDA 20/40/60, previous week). Bottom: PD arrays (FVGs, order blocks) with the dealing range, premium/discount and OTE."),
    ("02_live_15m_all_concepts.png", "Live 15-minute view: every concept at once", "Last 5 sessions: swings, previous-day high/low, displacement, FVGs and CE, order blocks and breakers, untouched equal-high/low pools, sweeps, MSS, 15m equilibrium and OTE."),
    ("03_concept_atlas.png", "Concept atlas: one clean real example per concept", "Twelve zoomed panels, each picked automatically from the 90 days, with the exact timestamps and prices in the caption."),
    ("04_setups_and_results.png", "Complete setups and results", "Sweep → MSS → FVG → limit entry at CE → stop beyond the sweep → target at the next pool → breakeven at +1R. Every setup in the 90 days is in the table."),
]


def write_page(res, name, out):
    import shutil
    dest = ROOT / "docs" / "practice" / name
    dest.mkdir(parents=True, exist_ok=True)
    for f, *_ in PAGE_IMAGES:
        shutil.copy(out / f, dest / f)
    shutil.copy(out / "setups.csv", dest / "setups.csv")
    m = res.m15
    S = res.setups
    t = S[S.R.notna()]
    rows = "".join(
        f"<tr><td>{r.mss_time:%d %b %H:%M}</td><td>{r.side}</td><td>{r.sweep_type}</td><td>{fmt(r.entry)}</td><td>{fmt(r.stop)}</td>"
        f"<td>{fmt(r.target) if pd.notna(r.target) else '—'}</td><td>{'' if pd.isna(r.rr) else f'{r.rr:.2f}'}</td><td>{r.result}</td>"
        f"<td style='color:var({'--up' if (r.R or 0) > 0 else '--dn' if (r.R or 0) < 0 else '--muted'});font-weight:600'>{'' if pd.isna(r.R) else f'{r.R:+.2f}'}</td>"
        f"<td>{r.grade}</td><td>{r.missing or '—'}</td></tr>" for r in S.itertuples())
    figs = "".join(f'<h2>{t_}</h2><p>{d_}</p><figure><a href="{f}"><img src="{f}" alt="{t_}" style="width:100%;height:auto;border-radius:6px"></a>'
                   f'<figcaption>Click to open full size.</figcaption></figure>' for f, t_, d_ in PAGE_IMAGES)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} practice · ICT concepts</title><link rel="stylesheet" href="../../assets/site.css"></head><body>
<header class="top"><a class="brand" href="../../index.html">ICT Swing Engine</a><span class="sp"></span><a href="../../index.html">All concepts</a></header>
<main style="margin:0 auto;max-width:1150px">
<div class="crumb">Practice on real data</div><h1>{name}: every concept marked on 90 days of 15-minute data</h1>
<p class="lede">{m.index[0]:%d %b %Y} to {m.index[-1]:%d %b %Y %H:%M} · {len(m)} bars. All marks are produced by the engine's rules; nothing is drawn by hand.</p>
<div class="card"><b>Bias (step 1):</b> {res.bias['sentence']}</div>
<div class="tags"><span class="tag">{len(res.sw15)} swings</span><span class="tag">{len(res.fvg15)} FVGs</span><span class="tag">{len(res.ob15)} order blocks</span>
<span class="tag">{len(res.sweeps15)} sweeps</span><span class="tag">{len(res.mss15)} MSS</span><span class="tag">{len(S)} setups · {len(t)} traded · avg {t.R.mean():+.2f}R</span></div>
{figs}
<h2>All setups</h2><div class="card" style="overflow-x:auto"><table><tr><th>MSS</th><th>side</th><th>swept</th><th>entry</th><th>stop</th><th>target</th><th>R:R</th><th>result</th><th>R</th><th>grade</th><th>missing</th></tr>{rows}</table></div>
<p><a href="setups.csv">Download setups.csv</a></p>
<div class="card warn"><b>Read this before trusting the numbers.</b> One instrument, 15-minute bars, {len(t)} trades, no costs or slippage, rules tuned on the same data. That is a learning exercise, not evidence of an edge.</div>
<div class="card"><small>Education only, not financial advice. Check current SEBI/exchange rules and consider a SEBI-registered advisor before using real capital.</small></div>
</main></body></html>"""
    (dest / "index.html").write_text(html)
    print(f"  ✓ page docs/practice/{name}/index.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="CSV name in data/raw without .csv, e.g. CNX500_15m")
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    name = a.name or a.symbol.replace("_15m", "")
    cfg = load_config()
    res = analyse(load_csv(a.symbol), cfg)
    out = ROOT / "reports" / name
    out.mkdir(parents=True, exist_ok=True)
    res.setups.to_csv(out / "setups.csv", index=False)
    for fn in (summary, htf_map, live_view, atlas, setups):
        fn(res, name, out)
        print("  ✓", fn.__name__)
    write_page(res, name, out)
    print(f"Images in reports/{name}/")


if __name__ == "__main__":
    main()
