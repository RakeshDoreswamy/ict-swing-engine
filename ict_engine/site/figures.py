"""Figures for every concept page: a schematic (how it should look) and, where the concept is
detectable, a real NIFTY example found by the engine's own detectors."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict_engine.detectors import basic as B
from ict_engine.detectors.swings import swing_table
from ict_engine.viz.svg import Chart, path_to_bars, synth

LVL_CLS = {1: "lv", 2: "lv-eq", 3: "lv-p"}


class Data:
    """Loads NIFTY 15m + daily + weekly once and pre-computes swings."""

    def __init__(self, cfg, m15: pd.DataFrame, daily: pd.DataFrame, weekly: pd.DataFrame):
        self.cfg, self.m15, self.daily, self.weekly = cfg, m15, daily, weekly
        self.sw15 = swing_table(m15, cfg)
        self.swd = swing_table(daily, cfg)
        self.atr15 = B.atr(m15)

    @staticmethod
    def window(df, i0, i1):
        i0, i1 = max(0, int(i0)), min(len(df), int(i1))
        return df.iloc[i0:i1], i0


def _marks(ch, sw, off, n, min_level=1, label=True):
    for r in sw.itertuples():
        i = r.bar - off
        if 0 <= i < n and r.level >= min_level:
            hi = r.side == "high"
            cls = "m-p" if r.level == 3 else ("m-a" if r.level == 2 else ("m-hi" if hi else "m-lo"))
            ch.mark(i, r.price, r.type if label else "", cls, above=hi, offset=10 + 4 * r.level)


def fig(svg, caption):
    return f"<figure>{svg}<figcaption>{caption}</figcaption></figure>"


# ---------------------------------------------------------------- 1 swing points
def swings_schematic():
    pts = [100, 102, 104, 103, 101, 102.5, 105, 107, 106, 104, 103, 105, 108, 110, 109, 106]
    df = synth(path_to_bars(pts, 0.4))
    ch = Chart(df, height=300, date_fmt=None)
    ch.highlight(7)
    ch.highlight(8, "hl")
    ch.mark(7, df.high.iloc[7], "STH: high above both neighbours", "m-hi")
    ch.mark(10, df.low.iloc[10], "STL", "m-lo", above=False)
    ch.mark(4, df.low.iloc[4], "STL", "m-lo", above=False)
    ch.mark(2, df.high.iloc[2], "STH", "m-hi")
    ch.mark(13, df.high.iloc[13], "STH", "m-hi")
    ch.arrow(8.6, df.low.iloc[8] - 0.6, 8.05, df.low.iloc[8] - 0.1, text="confirmed when this bar closes")
    return fig(ch.svg("Short-term swing schematic"),
               "Schematic: the shaded bar is a short-term high (STH) because its high is above the bar before and after it. "
               "You only know this once the next bar has closed lower, so it is <b>confirmed one bar late</b>.")


def swings_real(d: Data):
    df, off = d.window(d.m15, len(d.m15) - 90, len(d.m15))
    ch = Chart(df, date_fmt="%d %b %H:%M")
    _marks(ch, d.sw15[d.sw15.level == 1], off, len(df), label=False)
    for r in d.sw15[(d.sw15.bar >= off)].itertuples():
        i = r.bar - off
        ch.mark(i, r.price, "▼" if r.side == "high" else "▲", "m-hi" if r.side == "high" else "m-lo", above=r.side == "high", offset=8)
    return fig(ch.svg("NIFTY 15m swings"),
               f"Real NIFTY 15-minute chart, last 90 bars ({df.index[0]:%d %b} to {df.index[-1]:%d %b %Y}). "
               "Red ▼ = every confirmed swing high, green ▲ = every confirmed swing low, all found by <code>swing_table()</code>.")


# ---------------------------------------------------------------- 2 institutional swings
def levels_schematic():
    pts = [100, 103, 101, 105, 102, 104, 101.5, 108, 104, 106, 103, 111, 106, 107.5, 104, 106, 102, 104.5, 101]
    df = synth(path_to_bars(pts, 0.3))
    sw = swing_table(df, {"swings": {"fractal_left": 1, "fractal_right": 1, "strict": True, "break_on": "wick"}})
    ch = Chart(df, height=320, date_fmt=None)
    for r in sw[sw.side == "high"].itertuples():
        cls = {1: "m-hi", 2: "m-a", 3: "m-p"}[r.level]
        ch.mark(r.bar, r.price, r.type, cls, offset=10 + 6 * r.level)
    sth = sw[sw.side == "high"].sort_values("bar")
    for a, b in zip(sth.itertuples(), sth.iloc[1:].itertuples()):
        ch.layers.append(f'<line class="lv" stroke-dasharray="2 3" x1="{ch.x(a.bar):.1f}" y1="{ch.y(a.price):.1f}" x2="{ch.x(b.bar):.1f}" y2="{ch.y(b.price):.1f}"/>')
    ch.note("Dotted line joins the short-term highs. A peak in THAT line = ITH; a peak among ITHs = LTH.")
    return fig(ch.svg("Swing level schematic"),
               "Schematic: the same 3-point test is applied again to the list of swing highs. "
               "Grey = STH, blue = ITH (higher than the STH on each side), purple = LTH (higher than the ITH on each side).")


def levels_real(d: Data):
    df, off = d.window(d.daily, len(d.daily) - 200, len(d.daily))
    ch = Chart(df, date_fmt="%b %y")
    _marks(ch, d.swd, off, len(df), min_level=2)
    return fig(ch.svg("NIFTY daily ITH/LTH"),
               "Real NIFTY daily chart, last 200 sessions. Only intermediate (blue) and long-term (purple) swings are labelled. "
               "Notice how few there are: these are the levels a swing trader cares about.")


# ---------------------------------------------------------------- 3 open float
def open_float_real(d: Data):
    df, off = d.window(d.daily, len(d.daily) - 220, len(d.daily))
    ch = Chart(df, date_fmt="%b %y")
    last = df.close.iloc[-1]
    sw = d.swd[(d.swd.level >= 2) & (d.swd.bar >= off)]
    for r in sw.itertuples():
        i = r.bar - off
        if r.unbroken:
            cls = "lv-buy" if r.price > last else "lv-sell"
            ch.hline(r.price, i, None, cls, f"{r.type} {r.price:,.0f} open", dash=True)
        else:
            j = d.daily.index.get_loc(r.broken_date) - off
            ch.hline(r.price, i, j, "lv", None, dash=True)
    return fig(ch.svg("Open float NIFTY daily"),
               "Real NIFTY daily: intermediate/long-term swings. Grey dashes end where price <b>took</b> the level (its orders were filled). "
               "Coloured lines run to the right edge: still open. Red above price = buy-side liquidity, green below = sell-side liquidity.")


def open_float_schematic():
    pts = [100, 104, 106, 103, 101, 103, 105, 102, 99, 101, 104, 107.5, 105, 103, 104]
    df = synth(path_to_bars(pts, 0.3))
    ch = Chart(df, height=280, date_fmt=None)
    ch.hline(df.high.iloc[2], 2, 11, "lv", "old high: TAKEN at bar 11")
    ch.mark(11, df.high.iloc[11], "trades through", "m-a")
    ch.hline(df.low.iloc[8], 8, None, "lv-sell", "low: still OPEN")
    ch.hline(df.high.iloc[11], 11, None, "lv-buy", "new high: OPEN")
    return fig(ch.svg("Open float schematic"),
               "Schematic: a level stays in the open float until a later bar trades through it. Then it is spent and dropped.")


# ---------------------------------------------------------------- 4 liquidity pools
def pools_schematic():
    pts = [100, 103, 105.9, 104, 102, 104, 106, 104.5, 103, 105, 105.95, 103.5, 102, 103.5]
    df = synth(path_to_bars(pts, 0.25))
    ch = Chart(df, height=300, date_fmt=None)
    lvl = df.high.iloc[[2, 6, 10]].max()
    ch.zone(2, 13, lvl + 0.8, lvl + 0.05, "z-bear", "buy stops resting here (short sellers' stops + breakout buyers)")
    for i in (2, 6, 10):
        ch.mark(i, df.high.iloc[i], "=", "m-hi", offset=8)
    ch.hline(lvl, 2, 13, "lv-buy", "equal highs = buy-side pool")
    ch.hline(df.low.iloc[4], 4, 13, "lv-sell", "relative equal lows = sell-side pool")
    return fig(ch.svg("Equal highs schematic"),
               "Schematic: three highs at almost the same price look like 'strong resistance' to most traders, so stops pile up just above them. "
               "That cluster is a liquidity pool, and price is often drawn to it.")


def pools_real(d: Data):
    df, off = d.window(d.m15, len(d.m15) - 150, len(d.m15))
    ch = Chart(df, date_fmt="%d %b %H:%M")
    tol = 0.25 * float(d.atr15.iloc[-1])
    sw = d.sw15[d.sw15.bar >= off]
    groups = []
    for g in B.equal_levels(sw, tol):
        after = d.m15.iloc[max(g["bars"]) + 1:]
        still_open = (after.high <= g["price"]).all() if g["side"] == "high" else (after.low >= g["price"]).all()
        if still_open:
            groups.append(g)
    for g in groups[-4:]:
        i0 = min(g["bars"]) - off
        ch.hline(g["price"], i0, None, "lv-buy" if g["side"] == "high" else "lv-sell",
                 f"equal {'highs' if g['side'] == 'high' else 'lows'} x{g['touches']}")
        for b in g["bars"]:
            ch.mark(b - off, g["price"], "=", "m-hi" if g["side"] == "high" else "m-lo", above=g["side"] == "high", offset=7)
    days = pd.Series(df.index.date, index=df.index)
    ud = sorted(set(days))
    for k in range(1, len(ud)):
        prev = df[days.values == ud[k - 1]]
        cur_idx = np.nonzero(days.values == ud[k])[0]
        if len(cur_idx):
            ch.hline(prev.high.max(), cur_idx[0], cur_idx[-1], "lv-gold", None, dash=False)
            ch.hline(prev.low.min(), cur_idx[0], cur_idx[-1], "lv-gold", None, dash=False)
    ch.note("gold = previous day's high/low (intraday version of previous week's high/low)")
    return fig(ch.svg("NIFTY 15m pools"),
               f"Real NIFTY 15-minute, last 150 bars. Dashed lines are equal highs/lows (swings within {tol:,.0f} points, 0.25 × ATR) that are <b>still untouched</b>, so their stops are still there. "
               "Gold steps are the previous session's high and low, the levels every intraday trader watches.")


# ---------------------------------------------------------------- 5 sweeps
def sweep_schematic():
    pts = [106, 104, 102, 103.5, 105, 103, 102.05, 104, 105.5, 104, 103, 101, 104.5, 107, 109, 110.5]
    df = synth(path_to_bars(pts, 0.25))
    df.iloc[11, df.columns.get_loc("low")] = 99.6
    df.iloc[11, df.columns.get_loc("close")] = 102.6
    ch = Chart(df, height=310, date_fmt=None)
    lvl = min(df.low.iloc[2], df.low.iloc[6])
    ch.hline(lvl, 2, 15, "lv-sell", "equal lows (sell stops below)")
    ch.highlight(11)
    ch.mark(11, df.low.iloc[11], "wick takes the stops…", "m-lo", above=False)
    ch.mark(11, df.high.iloc[11], "…but closes back above", "m-a", offset=22)
    ch.arrow(12, 104, 15, 110, text="reversal")
    return fig(ch.svg("Sweep schematic"),
               "Schematic: a <b>sell-side sweep</b>. The wick runs the stops under the equal lows, but the candle <b>closes back inside</b>. "
               "Sellers who were stopped out have handed liquidity to buyers.")


def _pick_sweep(d: Data):
    s = B.sweeps(d.m15, d.sw15)
    s = s[s.swing_type.isin(["ITL", "ITH", "LTL", "LTH"])]
    s = s[s.bar < len(d.m15) - 12]
    return s.iloc[-1] if len(s) else None


def sweep_real(d: Data):
    r = _pick_sweep(d)
    if r is None:
        return ""
    df, off = d.window(d.m15, r.bar - 40, r.bar + 22)
    ch = Chart(df, date_fmt="%d %b %H:%M")
    sb = int(r.swing_bar) - off
    lo = r.side == "sell-side"
    ch.hline(r.level, max(sb, 0), r.bar - off, "lv-sell" if lo else "lv-buy", f"{r.swing_type} {r.level:,.0f}")
    ch.highlight(r.bar - off)
    ch.mark(r.bar - off, d.m15.low.iloc[r.bar] if lo else d.m15.high.iloc[r.bar], f"{r.side} sweep", "m-a", above=not lo)
    return fig(ch.svg("NIFTY 15m sweep"),
               f"Real NIFTY 15-minute: on {r.date:%d %b %H:%M} the candle traded beyond the {r.swing_type} at {r.level:,.0f} "
               "and closed back inside. Watch what price did in the bars after it.")


# ---------------------------------------------------------------- 6 displacement
def displacement_real(d: Data):
    df, off = d.window(d.m15, len(d.m15) - 110, len(d.m15))
    ch = Chart(df, date_fmt="%d %b %H:%M")
    disp = B.displacement(d.m15).iloc[off:]
    for k, v in enumerate(disp.values):
        if v:
            ch.highlight(k)
    ch.note("shaded = body larger than 1.2 × ATR(14)")
    return fig(ch.svg("Displacement NIFTY 15m"),
               f"Real NIFTY 15-minute, last 110 bars: {int((disp != 0).sum())} displacement candles are shaded. "
               "They are rare, and they are where the big moves (and the gaps they leave) come from.")


def displacement_schematic():
    rows = path_to_bars([100, 100.4, 99.9, 100.3, 100.0, 100.5, 100.2], 0.3) + [(100.2, 104.6, 100.0, 104.4), (104.4, 105, 103.6, 104.7)]
    df = synth(rows)
    ch = Chart(df, height=260, date_fmt=None)
    ch.highlight(7)
    ch.zone(0, 6, df.high.iloc[:7].max(), df.low.iloc[:7].min(), "z-neu", "normal candles: small bodies, overlap")
    ch.mark(7, df.high.iloc[7], "displacement: body ≫ ATR", "m-a")
    return fig(ch.svg("Displacement schematic"), "Schematic: one large-bodied candle breaks out of a quiet range with almost no wick. That is displacement.")


# ---------------------------------------------------------------- 7 FVG
def fvg_schematic():
    df = synth([(100, 101, 99.2, 100.6), (100.7, 105.2, 100.5, 105), (105, 106.4, 102.4, 106), (106, 106.5, 104, 104.4),
                (104.4, 104.8, 102.6, 103.2), (103.2, 106.2, 103, 106), (106, 108, 105.6, 107.8)])
    ch = Chart(df, height=320, date_fmt=None)
    ch.zone(1, 6, 102.4, 101, "z-bull")
    ch.hline(102.4, 2, 6, "lv-sell", "candle 3 low (FVG top)", dash=False)
    ch.hline(101.7, 1, 6, "lv-eq", "CE 50%")
    ch.hline(101, 0, 6, "lv-sell", "candle 1 high (FVG bottom)", dash=False)
    ch.mark(0, 99.2, "candle 1", "m-a", above=False)
    ch.mark(1, 105.2, "candle 2 (displacement)", "m-p")
    ch.mark(2, 106.4, "candle 3", "m-a")
    ch.mark(4, 102.6, "price returns into the gap", "m-lo", above=False, offset=30)
    return fig(ch.svg("FVG schematic"),
               "Schematic: candle 2 moved so fast that candle 1's high and candle 3's low never overlapped. "
               "The empty space is a <b>fair value gap</b>. Price often comes back to it, especially to the 50% line (CE).")


def fvg_real(d: Data):
    df, off = d.window(d.m15, len(d.m15) - 120, len(d.m15))
    ch = Chart(df, date_fmt="%d %b %H:%M")
    g = B.fvgs(d.m15, 0.3)
    g = g[g.bar >= off]
    open_ids = set(g[g.filled_bar.isna()].tail(3).index)
    for idx, r in zip(g.index, g.itertuples()):
        end = (r.filled_bar if pd.notna(r.filled_bar) else len(d.m15) - 1) - off
        cls = "z-bull" if r.side == "bull" else "z-bear"
        ch.zone(r.bar - off, end, r.top, r.bottom, cls)
        if idx in open_ids:
            ch.hline(r.ce, r.bar - off, None, "lv-eq", f"open {r.side} FVG, CE {r.ce:,.0f}")
    return fig(ch.svg("NIFTY 15m FVGs"),
               f"Real NIFTY 15-minute: {len(g)} FVGs of at least 0.3 × ATR in the last 120 bars. Each box ends when the gap is fully filled. "
               "Boxes that reach the right edge are still open.")


# ---------------------------------------------------------------- 8 order block
def ob_schematic():
    df = synth([(104, 104.5, 102.5, 103), (103, 103.4, 101.6, 102), (102, 102.4, 100.6, 101), (101.2, 106.5, 101, 106.2),
                (106.2, 108, 105.8, 107.7), (107.7, 108.2, 104.5, 105), (105, 105.4, 101.8, 102.3), (102.3, 106, 101.9, 105.8), (105.8, 109.5, 105.5, 109.2)])
    ch = Chart(df, height=320, date_fmt=None)
    ch.zone(2, 8, 102.4, 100.6, "z-bull", "bullish order block (last down candle)", "right")
    ch.hline(101.5, 2, 8, "lv-eq", "mean threshold 50%")
    ch.mark(3, 106.5, "displacement up", "m-a")
    ch.mark(6, 101.8, "return to OB = entry area", "m-lo", above=False)
    return fig(ch.svg("Order block schematic"),
               "Schematic: the last down-close candle before a strong move up is the <b>bullish order block</b>. "
               "ICT reads it as where the buying started. Price often returns to it, and its 50% (mean threshold) should hold.")


def ob_real(d: Data):
    obs = B.order_blocks(d.m15)
    obs = obs[(obs.side == "bull") & (obs.bar > len(d.m15) - 140) & (obs.bar < len(d.m15) - 15)]
    if obs.empty:
        return ""
    r = obs.iloc[-1]
    df, off = d.window(d.m15, r.bar - 25, min(r.bar + 45, len(d.m15)))
    ch = Chart(df, date_fmt="%d %b %H:%M")
    end = (r.breaker_bar if pd.notna(r.breaker_bar) else off + len(df) - 1) - off
    ch.zone(r.bar - off, end, r.top, r.bottom, "z-bull", f"bullish OB {r.bottom:,.0f}–{r.top:,.0f}")
    ch.hline(r["mean"], r.bar - off, end, "lv-eq", "mean")
    ch.highlight(int(r.displacement_bar) - off)
    return fig(ch.svg("NIFTY 15m order block"),
               f"Real NIFTY 15-minute: the down candle at {r.date:%d %b %H:%M} came just before a displacement candle (shaded). "
               "Its range is the order block. See whether later pullbacks respected it.")


# ---------------------------------------------------------------- 9 breaker
def breaker_schematic():
    df = synth([(101, 101.4, 99.8, 100.2), (100.2, 104, 100, 103.8), (103.8, 106, 103.5, 105.6), (105.6, 106.4, 104.4, 104.8),
                (104.8, 107.2, 104.6, 106.9), (106.9, 107.1, 102, 102.3), (102.3, 102.6, 98.8, 99.2), (99.2, 101.3, 99, 101),
                (101, 101.1, 97.5, 97.8), (97.8, 98.2, 95.6, 96)])
    ch = Chart(df, height=320, date_fmt=None)
    ch.zone(0, 9, 101.4, 99.8, "z-bear", "failed bullish OB = bearish breaker", "right")
    ch.mark(4, 107.2, "1. high swept", "m-a")
    ch.mark(6, 98.8, "2. closes below the OB", "m-hi", above=False)
    ch.mark(7, 101.3, "3. retest from below = short entry", "m-p", offset=30)
    return fig(ch.svg("Breaker schematic"),
               "Schematic: a bullish order block is broken by a close below it after a high was swept. "
               "The old support zone now acts as resistance: a <b>bearish breaker</b>.")


def breaker_real(d: Data):
    obs = B.order_blocks(d.m15)
    obs = obs[obs.breaker_bar.notna()]
    obs = obs[(obs.breaker_bar < len(d.m15) - 10)]
    if obs.empty:
        return ""
    r = obs.iloc[-1]
    bb = int(r.breaker_bar)
    df, off = d.window(d.m15, r.bar - 15, min(bb + 30, len(d.m15)))
    ch = Chart(df, date_fmt="%d %b %H:%M")
    cls_ob = "z-bull" if r.side == "bull" else "z-bear"
    cls_br = "z-bear" if r.side == "bull" else "z-bull"
    ch.zone(r.bar - off, bb - off, r.top, r.bottom, cls_ob, f"{r.side} OB")
    ch.zone(bb - off, len(df) - 1, r.top, r.bottom, cls_br, "now a breaker", label_side="right")
    ch.highlight(bb - off)
    return fig(ch.svg("NIFTY 15m breaker"),
               f"Real NIFTY 15-minute: a {r.side} order block from {r.date:%d %b %H:%M} was closed through at {d.m15.index[bb]:%d %b %H:%M} (shaded). "
               "From then on the engine treats it as a breaker from the other side.")


# ---------------------------------------------------------------- 10 premium/discount + 11 OTE
def _range_chart(d: Data, df, off, rng, show_ote=False, title=""):
    intraday = (df.index.normalize() != df.index).any()
    ch = Chart(df, date_fmt="%d %b %H:%M" if intraday else "%d %b %y")
    i0 = min(rng["high_bar"], rng["low_bar"]) - off
    ch.zone(i0, len(df) - 1, rng["high"], rng["eq"], "z-bear", "PREMIUM: sell zone", label_side="right")
    ch.zone(i0, len(df) - 1, rng["eq"], rng["low"], "z-bull", "DISCOUNT: buy zone", label_side="right")
    ch.hline(rng["eq"], i0, None, "lv-eq", f"EQ {rng['eq']:,.0f}")
    if show_ote:
        ch.zone(i0, len(df) - 1, max(rng["ote_62"], rng["ote_79"]), min(rng["ote_62"], rng["ote_79"]), "z-gold", "OTE 62–79%")
        ch.hline(rng["ote_705"], i0, None, "lv-gold", "70.5%")
    ch.mark(rng["high_bar"] - off, rng["high"], f"range high {rng['high']:,.0f}", "m-hi")
    ch.mark(rng["low_bar"] - off, rng["low"], f"range low {rng['low']:,.0f}", "m-lo", above=False)
    return ch


def pd_real(d: Data):
    sw = d.sw15[d.sw15.level >= 2]
    rng = B.dealing_range(sw)
    i0 = min(rng["high_bar"], rng["low_bar"])
    df, off = d.window(d.m15, i0 - 15, len(d.m15))
    ch = _range_chart(d, df, off, rng)
    return fig(ch.svg("Premium discount NIFTY 15m"),
               f"Real NIFTY 15-minute: the dealing range runs from the latest intermediate low ({rng['low']:,.0f}) to the latest intermediate high ({rng['high']:,.0f}). "
               f"Above {rng['eq']:,.0f} is premium (sell only), below is discount (buy only).")


def pd_schematic():
    pts = [100, 98, 96, 97, 99, 102, 105, 108, 110, 108, 106, 104.5, 103, 104, 106, 109]
    df = synth(path_to_bars(pts, 0.3))
    rng = {"high": df.high.iloc[8], "low": df.low.iloc[2], "high_bar": 8, "low_bar": 2}
    rng["eq"] = (rng["high"] + rng["low"]) / 2
    ch = Chart(df, height=300, date_fmt=None)
    ch.zone(2, 15, rng["high"], rng["eq"], "z-bear", "premium (expensive)", "right")
    ch.zone(2, 15, rng["eq"], rng["low"], "z-bull", "discount (cheap)", "right")
    ch.hline(rng["eq"], 2, None, "lv-eq", "equilibrium 50%")
    ch.mark(12, df.low.iloc[12], "buy here, in discount", "m-lo", above=False)
    return fig(ch.svg("Premium discount schematic"),
               "Schematic: split the range from swing low to swing high in half. Smart money buys below half price and sells above it.")


def ote_schematic():
    pts = [100, 98.5, 97, 99, 102, 105, 108, 111, 113, 110.5, 107.5, 105, 103.3, 106, 110, 114, 117]
    df = synth(path_to_bars(pts, 0.3))
    hi, lo = df.high.iloc[8], df.low.iloc[2]
    r = hi - lo
    ch = Chart(df, height=320, date_fmt=None)
    ch.zone(8, 16, hi - 0.62 * r, hi - 0.79 * r, "z-gold", "OTE: 62% to 79% retracement")
    ch.hline(hi - 0.705 * r, 8, None, "lv-gold", "70.5% sweet spot")
    ch.hline(hi - 0.5 * r, 8, None, "lv-eq", "50%")
    ch.arrow(2, lo, 8, hi, text="impulse leg")
    ch.mark(12, df.low.iloc[12], "entry", "m-lo", above=False)
    ch.hline(lo, 2, None, "lv-sell", "stop below the leg's low")
    return fig(ch.svg("OTE schematic"),
               "Schematic: after an impulse up, draw a fib from the low (100%) to the high (0%). "
               "The 62 to 79% pullback is the <b>optimal trade entry</b>: deep in discount, close to the stop, far from the target.")


def ote_real(d: Data):
    sw = d.swd[d.swd.level >= 2]
    rng = B.dealing_range(sw)
    i0 = min(rng["high_bar"], rng["low_bar"])
    df, off = d.window(d.daily, i0 - 15, len(d.daily))
    ch = _range_chart(d, df, off, rng, show_ote=True)
    leg = "up" if rng["up_leg"] else "down"
    return fig(ch.svg("OTE NIFTY daily"),
               f"Real NIFTY daily: last intermediate leg ({leg}) from {rng['low']:,.0f} to {rng['high']:,.0f}. "
               f"The gold band is its OTE ({min(rng['ote_62'], rng['ote_79']):,.0f}–{max(rng['ote_62'], rng['ote_79']):,.0f}).")


# ---------------------------------------------------------------- 12 HTF PD arrays
def pd_arrays_real(d: Data):
    df, off = d.window(d.daily, len(d.daily) - 130, len(d.daily))
    ch = Chart(df, date_fmt="%b %y")
    last = len(d.daily) - 1
    g = B.fvgs(d.daily, 0.2)
    for r in g[(g.bar >= off) & g.filled_bar.isna()].tail(3).itertuples():
        ch.zone(r.bar - off, last - off, r.top, r.bottom, "z-bull" if r.side == "bull" else "z-bear", f"{r.side} FVG", "right")
    obs = B.order_blocks(d.daily)
    for r in obs[(obs.bar >= off) & obs.breaker_bar.isna()].tail(3).itertuples():
        ch.zone(r.bar - off, last - off, r.top, r.bottom, "z-neu", f"{r.side} OB", "right")
    sw = d.swd[(d.swd.level >= 2) & d.swd.unbroken & (d.swd.bar >= off)]
    for r in sw.itertuples():
        ch.hline(r.price, r.bar - off, None, "lv-p", f"{r.type} {r.price:,.0f}")
    wk = d.weekly
    pw = wk.iloc[-2]
    ch.hline(pw.high, len(df) - 6, None, "lv-gold", "prev week high", dash=False)
    ch.hline(pw.low, len(df) - 6, None, "lv-gold", "prev week low", dash=False)
    return fig(ch.svg("HTF PD arrays NIFTY daily"),
               "Real NIFTY daily, last 130 sessions: every still-valid zone the engine sees. Unfilled FVGs, unbroken order blocks, "
               "open intermediate/long-term swings (purple), and the previous week's high/low (gold). This map is your trade-location list.")


# ---------------------------------------------------------------- 13 MSS + 14 setup progression
def mss_schematic():
    pts = [112, 110, 111, 108, 109.5, 106, 107.5, 104.5, 103, 105, 107.5, 110, 109, 108, 111.5, 114]
    df = synth(path_to_bars(pts, 0.3))
    df.iloc[8, df.columns.get_loc("low")] = 101.8
    df.iloc[10, :4] = (105, 108.9, 104.8, 108.7)
    ch = Chart(df, height=320, date_fmt=None)
    ch.hline(df.high.iloc[6], 6, 10, "lv-buy", None)
    ch.mark(6, df.high.iloc[6], "last short-term high", "m-hi", offset=12)
    ch.mark(8, df.low.iloc[8], "1. sweep of lows", "m-lo", above=False)
    ch.highlight(10)
    ch.mark(10, df.high.iloc[10], "2. CLOSE above it with displacement = MSS", "m-a", offset=26)
    ch.zone(9, 15, df.low.iloc[11], df.high.iloc[9], "z-bull", "3. FVG left behind = entry", "right")
    ch.note("lower highs and lower lows → sweep → MSS")
    return fig(ch.svg("MSS schematic"),
               "Schematic: a downtrend sweeps a low, then a displacement candle <b>closes</b> above the last short-term high. "
               "The short-term structure has shifted from down to up.")


def _pick_mss_setup(d: Data):
    ms = B.mss_events(d.m15, d.sw15)
    sw = B.sweeps(d.m15, d.sw15)
    g = B.fvgs(d.m15, 0.2)
    best = None
    for r in ms.itertuples():
        want = "sell-side" if r.side == "bull" else "buy-side"
        prior = sw[(sw.side == want) & (sw.bar < r.bar) & (sw.bar >= r.bar - 15)]
        f = g[(g.side == r.side) & (g.bar >= r.bar - 1) & (g.bar <= r.bar + 1)]
        if len(prior) and len(f) and r.bar < len(d.m15) - 15:
            best = (r, prior.iloc[-1], f.iloc[0])
    return best


def mss_real(d: Data, composite=False):
    pick = _pick_mss_setup(d)
    if not pick:
        return ""
    m, s, f = pick
    df, off = d.window(d.m15, s.bar - 14, m.bar + 26)
    ch = Chart(df, date_fmt="%d %b %H:%M")
    bull = m.side == "bull"
    ch.hline(m.level, max(int(m.swing_bar) - off, 0), m.bar - off, "lv-buy" if bull else "lv-sell", None)
    ch.mark(max(int(m.swing_bar) - off, 0), m.level, f"last {'STH' if bull else 'STL'} {m.level:,.0f}", "m-hi" if bull else "m-lo", above=bull, offset=12)
    ch.mark(s.bar - off, d.m15.low.iloc[s.bar] if bull else d.m15.high.iloc[s.bar], "1 sweep" if composite else "sweep", "m-lo" if bull else "m-hi", above=not bull)
    ch.highlight(m.bar - off)
    ch.mark(m.bar - off, d.m15.high.iloc[m.bar] if bull else d.m15.low.iloc[m.bar], "2 MSS (close)" if composite else "MSS", "m-a", above=bull, offset=24)
    ch.zone(f.bar - off, len(df) - 1, f.top, f.bottom, "z-bull" if bull else "z-bear")
    ch.mark(f.bar - off + 3, f.bottom if bull else f.top, "3 FVG entry zone" if composite else "FVG", "m-lo" if bull else "m-hi", above=not bull, offset=26)
    if composite:
        risk_stop = d.m15.low.iloc[s.bar] if bull else d.m15.high.iloc[s.bar]
        ch.hline(f.ce, f.bar - off, None, "lv-eq", f"4 limit at CE {f.ce:,.0f}")
        ch.hline(risk_stop, s.bar - off, None, "lv-p", f"5 stop beyond sweep {risk_stop:,.0f}")
        ch.hline(f.ce, f.bar - off, None, "lv-eq", None)
    cap = (f"Real NIFTY 15-minute: {s.side} sweep at {s.date:%d %b %H:%M}, then a {'bullish' if bull else 'bearish'} MSS when a candle closed "
           f"{'above' if bull else 'below'} {m.level:,.0f} at {m.date:%H:%M}, leaving an FVG.")
    return fig(ch.svg("NIFTY 15m MSS"), cap + (" Every step of the setup, found automatically." if composite else ""))


def progression_flow():
    steps = [("1 Bias", "weekly: up / down / range"), ("2 Location", "at an HTF zone, in discount"), ("3 Liquidity", "pool swept or clear target"),
             ("4 Confirmation", "daily MSS by close"), ("5 Entry", "FVG / OB / OTE + stop + target")]
    w, bw, gap = 1010, 182, 23
    out = [f'<svg class="chart" viewBox="0 0 {w} 120" role="img" aria-label="Setup progression">',
           '<defs><marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ah"/></marker></defs>']
    for k, (t, s) in enumerate(steps):
        x = 8 + k * (bw + gap)
        out.append(f'<rect class="flow-box{" on" if k == 3 else ""}" x="{x}" y="22" width="{bw}" height="70" rx="10"/>'
                   f'<text class="flow-t" x="{x + bw / 2}" y="52" text-anchor="middle">{t}</text>'
                   f'<text class="flow-s" x="{x + bw / 2}" y="72" text-anchor="middle">{s}</text>')
        if k < 4:
            out.append(f'<line class="arr" x1="{x + bw + 2}" y1="57" x2="{x + bw + gap - 2}" y2="57" marker-end="url(#ah2)"/>')
    out.append("</svg>")
    return fig("".join(out), "The setup is a sequence. Skip a step and it is not an ICT setup, it is a guess. Step 4 is the trigger.")


# ---------------------------------------------------------------- 15 entries, 17 management
def entries_schematic():
    df = synth(path_to_bars([108, 106, 104, 102.5, 101, 103.5, 106.5, 105.5, 104.6, 106, 108.5, 111, 113], 0.3))
    ch = Chart(df, height=320, date_fmt=None)
    ch.zone(5, 12, 104.0, 103.0, "z-bull", "FVG")
    ch.hline(103.5, 5, None, "lv-eq", "LIMIT at CE: better price")
    ch.hline(106.9, 6, None, "lv-gold", "STOP above MSS high: sure fill")
    ch.hline(df.low.iloc[4] - 0.4, 4, None, "lv-p", "stop-loss below sweep low")
    ch.hline(113, 0, None, "lv-buy", "target: next buy-side pool")
    return fig(ch.svg("Entry models"), "Schematic: two ways into the same setup. The limit entry gets a better R:R but can be missed. The stop entry never misses but pays more.")


def management_schematic():
    df = synth(path_to_bars([100, 101, 103, 102, 104.5, 106, 105, 107.5, 109, 108, 110.5, 112, 111, 113.5, 115], 0.3))
    ch = Chart(df, height=320, date_fmt=None)
    entry, stop = 100.3, 98.5
    r = entry - stop
    ch.hline(entry, 0, None, "lv-eq", "entry")
    ch.hline(stop, 0, 3, "lv-p", "initial stop (−1R)", dash=False)
    ch.hline(entry, 3, 6, "lv-p", None, dash=False)
    ch.mark(3, entry, "+1R hit → stop to breakeven", "m-p", above=False, offset=20)
    ch.hline(df.low.iloc[6], 6, 9, "lv-p", None, dash=False)
    ch.hline(df.low.iloc[9], 9, 14, "lv-p", "trail under each new swing low", dash=False)
    ch.mark(8, df.high.iloc[8], "50% off at first pool", "m-a")
    ch.mark(14, df.high.iloc[14], f"runner to target ≈ +{(df.high.iloc[14] - entry) / r:.1f}R", "m-lo")
    return fig(ch.svg("Trade management"), "Schematic: the purple step-line is the stop. It only ever moves in your favour: breakeven, then under each new swing low.")


# ---------------------------------------------------------------- 16 money management
def drawdown_chart():
    w, h, pl, pb = 960, 260, 50, 30
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Losing streak">']
    risks = [(1, "lv-sell"), (2, "lv-eq"), (5, "lv-buy")]
    n = 15
    for k in range(5):
        v = 100 - k * 12.5
        y = 10 + (100 - v) / 55 * (h - pb - 10) if v >= 45 else None
    for v in (100, 90, 80, 70, 60, 50):
        y = 10 + (100 - v) / 55 * (h - pb - 10)
        out.append(f'<line class="grid" x1="{pl}" x2="{w - 120}" y1="{y:.1f}" y2="{y:.1f}"/><text class="ax" x="{pl - 8}" y="{y + 4:.1f}" text-anchor="end">{v}%</text>')
    for r, cls in risks:
        pts = []
        eq = 100.0
        for i in range(n + 1):
            x = pl + i * (w - 120 - pl) / n
            y = 10 + (100 - eq) / 55 * (h - pb - 10)
            pts.append(f"{x:.1f},{y:.1f}")
            eq *= 1 - r / 100
        out.append(f'<polyline class="{cls}" fill="none" stroke-width="2.4" points="{" ".join(pts)}"/>')
        eq_end = 100 * (1 - r / 100) ** n
        out.append(f'<text class="lbl {cls}-t" x="{w - 112}" y="{10 + (100 - eq_end) / 55 * (h - pb - 10) + 4:.1f}">{r}% risk → {eq_end:.0f}%</text>')
    for i in range(0, n + 1, 3):
        out.append(f'<text class="ax" x="{pl + i * (w - 120 - pl) / n:.1f}" y="{h - 8}" text-anchor="middle">{i} losses</text>')
    out.append("</svg>")
    return fig("".join(out), "Same 15-trade losing streak (it happens to every strategy). At 1% risk you keep 86% of capital; at 5% you keep 46% and need +117% to get back.")


# ---------------------------------------------------------------- 18 event filters (gaps)
def gaps_real(d: Data):
    dd = d.daily.copy()
    gap = (dd.open / dd.close.shift(1) - 1) * 100
    df, off = d.window(dd, len(dd) - 250, len(dd))
    ch = Chart(df, date_fmt="%b %y")
    top = gap.iloc[off:].abs().nlargest(6)
    for dt, v in top.items():
        i = df.index.get_loc(dt)
        ch.highlight(i)
        g = gap.loc[dt]
        ch.mark(i, df.high.iloc[i] if g > 0 else df.low.iloc[i], f"{g:+.1f}%", "m-a", above=g > 0)
    return fig(ch.svg("NIFTY gaps"),
               "Real NIFTY daily, last 250 sessions: the 6 largest overnight gaps. A stop sitting inside any of these gaps would have been filled at the open, "
               "far worse than planned. That is why the engine pads position size and avoids event days.")


# ---------------------------------------------------------------- 19 IPDA, 20 quarterly shifts
def ipda_real(d: Data):
    df, off = d.window(d.daily, len(d.daily) - 90, len(d.daily))
    ch = Chart(df, date_fmt="%d %b")
    rngs = B.ipda_ranges(d.daily)
    cls = {20: "lv-eq", 40: "lv-gold", 60: "lv-p"}
    for side in ("high", "low"):
        seen = {}
        for n, r in rngs.items():
            seen.setdefault(round(r[side], 2), []).append(n)
        for price, ns in seen.items():
            n = ns[0]
            ch.hline(price, max(len(df) - 1 - ns[-1], 0), None, cls[n], f"{' & '.join(map(str, ns))}d {side} {price:,.0f}", dash=False)
    return fig(ch.svg("IPDA ranges"), "Real NIFTY daily: the 20, 40 and 60-session highs and lows. Each line starts where its lookback window begins.")


def quarterly_real(d: Data):
    df = d.daily
    ch = Chart(df, date_fmt="%b %y")
    q = B.quarterly_shifts(df, d.cfg["ipda"]["quarterly_shift_range"])
    hi = df.high.rolling(60).max().shift(1)
    lo = df.low.rolling(60).min().shift(1)
    pts_h = " ".join(f"{ch.x(i):.1f},{ch.y(v):.1f}" for i, v in enumerate(hi) if pd.notna(v))
    pts_l = " ".join(f"{ch.x(i):.1f},{ch.y(v):.1f}" for i, v in enumerate(lo) if pd.notna(v))
    ch.layers.append(f'<polyline class="lv" fill="none" points="{pts_h}"/><polyline class="lv" fill="none" points="{pts_l}"/>')
    for r in q.itertuples():
        up = r.direction == "up"
        ch.highlight(r.bar)
        ch.mark(r.bar, df.high.iloc[r.bar] if up else df.low.iloc[r.bar], f"shift {r.direction} {r.date:%b %y}", "m-lo" if up else "m-hi", above=up, offset=22)
    gaps = q.date.diff().dt.days.dropna()
    avg = f"{gaps.mean() / 30:.1f} months" if len(gaps) else "n/a"
    return fig(ch.svg("Quarterly shifts"),
               f"Real NIFTY daily, full history: grey lines are the prior 60-session high/low. Each label is a close through the range in the opposite direction "
               f"to the last break. Average time between shifts here: {avg}.")


# ---------------------------------------------------------------- 21 seasonality
def seasonal_real(d: Data):
    m = d.daily.close.resample("ME").last().pct_change().dropna() * 100
    by = m.groupby(m.index.month)
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    w, h, pl = 960, 260, 50
    mid = h / 2
    vals = {k: (g.mean(), len(g)) for k, g in by}
    mx = max(abs(v[0]) for v in vals.values()) or 1
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Seasonality">',
           f'<line class="grid" x1="{pl}" x2="{w - 10}" y1="{mid}" y2="{mid}"/>']
    bw = (w - pl - 20) / 12
    for k in range(1, 13):
        x = pl + (k - 1) * bw + bw * 0.15
        if k in vals:
            v, cnt = vals[k]
            hh = abs(v) / mx * (mid - 30)
            y = mid - hh if v >= 0 else mid
            out.append(f'<rect class="{"bar-up" if v >= 0 else "bar-dn"}" x="{x:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" height="{hh:.1f}" rx="3"/>'
                       f'<text class="lbl" x="{x + bw * 0.35:.1f}" y="{(y - 5) if v >= 0 else (y + hh + 13):.1f}" text-anchor="middle">{v:+.1f}% (n={cnt})</text>')
        out.append(f'<text class="ax" x="{x + bw * 0.35:.1f}" y="{h - 6}" text-anchor="middle">{names[k - 1]}</text>')
    out.append("</svg>")
    return fig("".join(out),
               f"Real NIFTY average return by calendar month, {m.index[0]:%b %Y} to {m.index[-1]:%b %Y}. With n = 1 or 2 per month this proves <b>nothing</b>: "
               "the engine needs 10+ years and a t-stat above 2 before seasonality may influence bias.")


# ---------------------------------------------------------------- 25 lookahead
def lookahead_schematic():
    df = synth(path_to_bars([100, 101.5, 103, 104.5, 103.5, 102, 101, 102.5, 104, 106], 0.3))
    ch = Chart(df, height=280, date_fmt=None)
    ch.highlight(3)
    ch.highlight(4)
    ch.mark(3, df.high.iloc[3], "bar 3: looks like a high…", "m-hi", offset=26)
    ch.mark(4, df.low.iloc[4], "…only CONFIRMED when bar 4 closes", "m-a", above=False, offset=40)
    ch.note("A backtest that sells at bar 3's high because 'it was the swing high' is using the future.")
    return fig(ch.svg("Lookahead"), "Schematic: the most common backtest lie. The engine stores <code>confirm_date</code> for every swing and only lets signals use what was confirmed.")
