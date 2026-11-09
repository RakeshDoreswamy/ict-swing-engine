"""First-pass ICT detectors (used by the concept site and the learn walkthroughs).

These are the simple, documented versions of the rules. Modules 2 to 7 will harden them
(ranking, freshness, point-in-time views), but the definitions here are already exact.
All functions work on any timeframe (15m, daily, weekly).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (simple mean of true range over ``period`` bars)."""
    prev = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def displacement(df: pd.DataFrame, mult: float = 1.2, period: int = 14) -> pd.Series:
    """+1 / -1 where the candle body exceeds ``mult`` x ATR (of the PRIOR bars), else 0."""
    body = df["close"] - df["open"]
    a = atr(df, period).shift(1).bfill()
    return pd.Series(np.where(body.abs() > mult * a, np.sign(body), 0), index=df.index).astype(int)


def fvgs(df: pd.DataFrame, min_size_atr: float = 0.0, period: int = 14, same_session: bool = True) -> pd.DataFrame:
    """Fair value gaps.

    Bullish FVG at middle bar i: low[i+1] > high[i-1]; zone = [high[i-1], low[i+1]].
    Bearish FVG at middle bar i: high[i+1] < low[i-1]; zone = [high[i+1], low[i-1]].
    CE (consequent encroachment) = zone midpoint. Known at the close of bar i+1.
    ``filled_bar`` = first later bar that trades through the far edge (bullish: low <= bottom).
    ``inverse_bar`` = first later bar that CLOSES through the far edge (gap becomes an inverse FVG).
    On intraday data with ``same_session``, the 3 candles must share one trading day, so the
    overnight opening gap (a different ICT concept) is not counted as an FVG.
    """
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    a = atr(df, period).to_numpy()
    day = df.index.normalize()
    intraday = len(df) > 1 and (day[1:] == day[:-1]).any()
    rows = []
    for i in range(1, len(df) - 1):
        if same_session and intraday and day[i - 1] != day[i + 1]:
            continue
        for side, top, bot in (("bull", l[i + 1], h[i - 1]), ("bear", l[i - 1], h[i + 1])):
            if top > bot and top - bot >= min_size_atr * a[i]:
                after = slice(i + 2, None)
                if side == "bull":
                    fill = np.nonzero(l[after] <= bot)[0]
                    inv = np.nonzero(c[after] < bot)[0]
                    touch = np.nonzero(l[after] <= top)[0]
                else:
                    fill = np.nonzero(h[after] >= top)[0]
                    inv = np.nonzero(c[after] > top)[0]
                    touch = np.nonzero(h[after] >= bot)[0]
                rows.append({
                    "bar": i, "date": df.index[i], "side": side, "top": top, "bottom": bot,
                    "ce": (top + bot) / 2, "size": top - bot, "confirm_bar": i + 1,
                    "first_touch_bar": i + 2 + touch[0] if touch.size else None,
                    "filled_bar": i + 2 + fill[0] if fill.size else None,
                    "inverse_bar": i + 2 + inv[0] if inv.size else None,
                })
    return pd.DataFrame(rows)


def order_blocks(df: pd.DataFrame, mult: float = 1.2, lookback: int = 5, period: int = 14) -> pd.DataFrame:
    """Order blocks.

    Bullish OB: the last DOWN-close candle within ``lookback`` bars before a bullish
    displacement candle. Zone = that candle's [low, high]; mean threshold = its 50%.
    Bearish OB mirrors it. ``breaker_bar`` = first later bar that CLOSES through the far side
    of the zone (bullish OB: close < low), after which it acts as a breaker block.
    """
    disp = displacement(df, mult, period).to_numpy()
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    rows, seen = [], set()
    for j in np.nonzero(disp)[0]:
        want_down = disp[j] > 0
        for i in range(j - 1, max(j - lookback, 0) - 1, -1):
            if (c[i] < o[i]) == want_down and c[i] != o[i]:
                if (i, disp[j]) in seen:
                    break
                seen.add((i, disp[j]))
                side = "bull" if want_down else "bear"
                later = slice(j + 1, None)
                brk = np.nonzero(c[later] < l[i] if side == "bull" else c[later] > h[i])[0]
                rows.append({
                    "bar": i, "date": df.index[i], "side": side, "top": h[i], "bottom": l[i],
                    "mean": (h[i] + l[i]) / 2, "displacement_bar": int(j),
                    "breaker_bar": j + 1 + brk[0] if brk.size else None,
                })
                break
    return pd.DataFrame(rows)


def equal_levels(swings: pd.DataFrame, tol: float) -> list[dict]:
    """Groups of 2+ swing highs (or lows) whose prices sit within ``tol`` of each other."""
    out = []
    for side in ("high", "low"):
        s = swings[swings.side == side].sort_values("price")
        group = []
        for r in s.itertuples():
            if group and r.price - group[0].price > tol:
                if len(group) >= 2:
                    out.append(_grp(group, side))
                group = []
            group.append(r)
        if len(group) >= 2:
            out.append(_grp(group, side))
    return out


def _grp(group, side):
    return {"side": side, "price": max(g.price for g in group) if side == "high" else min(g.price for g in group),
            "dates": [g.date for g in group], "bars": [g.bar for g in group], "touches": len(group)}


def sweeps(df: pd.DataFrame, swings: pd.DataFrame) -> pd.DataFrame:
    """Liquidity sweeps of confirmed swing points.

    Buy-side sweep: a bar whose HIGH trades above an earlier, still-unbroken swing high but
    whose CLOSE is back below it. Sell-side sweep mirrors it on lows. Only swings confirmed
    before the sweep bar count.
    """
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    rows = []
    for s in swings.itertuples():
        start = s.bar + 1
        for j in range(start, len(df)):
            if s.side == "high" and h[j] > s.price:
                if c[j] < s.price and j > s.bar + 1:
                    rows.append({"bar": j, "date": df.index[j], "side": "buy-side", "level": s.price,
                                 "swing_bar": s.bar, "swing_type": s.type})
                break
            if s.side == "low" and l[j] < s.price:
                if c[j] > s.price and j > s.bar + 1:
                    rows.append({"bar": j, "date": df.index[j], "side": "sell-side", "level": s.price,
                                 "swing_bar": s.bar, "swing_type": s.type})
                break
    return pd.DataFrame(rows).sort_values("bar").reset_index(drop=True) if rows else pd.DataFrame()


def mss_events(df: pd.DataFrame, swings: pd.DataFrame, mult: float = 1.0, period: int = 14) -> pd.DataFrame:
    """Market structure shifts.

    Bullish MSS: a bar that CLOSES above the most recent confirmed short-term high, with a body
    larger than ``mult`` x ATR, while the prior trend leg was down (the last confirmed swing
    low was lower than the one before it). Bearish mirrors it.
    """
    disp_ok = (df["close"] - df["open"]).abs().to_numpy() > mult * atr(df, period).shift(1).bfill().to_numpy()
    c = df["close"].to_numpy()
    sh = swings[swings.side == "high"].sort_values("bar")
    sl = swings[swings.side == "low"].sort_values("bar")
    rows, used = [], set()
    for j in range(len(df)):
        for side, mine, other, cmp in (("bull", sh, sl, lambda x, y: x > y), ("bear", sl, sh, lambda x, y: x < y)):
            known = mine[mine.bar + 1 < j]
            prior = other[other.bar + 1 < j]
            if known.empty or len(prior) < 2:
                continue
            last = known.iloc[-1]
            if (side, last.bar) in used:
                continue
            trend_against = prior.price.iloc[-1] < prior.price.iloc[-2] if side == "bull" else prior.price.iloc[-1] > prior.price.iloc[-2]
            if cmp(c[j], last.price) and disp_ok[j] and trend_against:
                used.add((side, last.bar))
                rows.append({"bar": j, "date": df.index[j], "side": side, "level": last.price, "swing_bar": int(last.bar)})
    return pd.DataFrame(rows)


def dealing_range(swings: pd.DataFrame, upto_bar: int | None = None) -> dict | None:
    """Most recent confirmed high and low swings (any level) -> range, equilibrium, OTE levels."""
    s = swings if upto_bar is None else swings[swings.bar <= upto_bar]
    hi, lo = s[s.side == "high"], s[s.side == "low"]
    if hi.empty or lo.empty:
        return None
    hi, lo = hi.iloc[-1], lo.iloc[-1]
    top, bot = hi.price, lo.price
    up_leg = lo.bar < hi.bar  # low then high = impulse up, retracement goes down
    rng = top - bot

    def lvl(f):  # retracement level f of the leg
        return top - f * rng if up_leg else bot + f * rng

    return {"high": top, "low": bot, "high_bar": int(hi.bar), "low_bar": int(lo.bar), "up_leg": up_leg,
            "eq": (top + bot) / 2, "ote_62": lvl(0.62), "ote_705": lvl(0.705), "ote_79": lvl(0.79)}


def ipda_ranges(df: pd.DataFrame, lookbacks=(20, 40, 60)) -> dict:
    """High/low of the last N bars for each IPDA lookback (excluding the current bar)."""
    out = {}
    for n in lookbacks:
        w = df.iloc[-n - 1 : -1]
        out[n] = {"high": w["high"].max(), "low": w["low"].min(),
                  "high_date": w["high"].idxmax(), "low_date": w["low"].idxmin()}
    return out


def quarterly_shifts(df: pd.DataFrame, n: int = 60) -> pd.DataFrame:
    """Bars where the close breaks the prior ``n``-bar range in the opposite direction to the last break."""
    hi = df["high"].rolling(n).max().shift(1)
    lo = df["low"].rolling(n).min().shift(1)
    rows, last = [], 0
    for i, (dt, r) in enumerate(df.iterrows()):
        if pd.isna(hi.iloc[i]):
            continue
        d = 1 if r.close > hi.iloc[i] else -1 if r.close < lo.iloc[i] else 0
        if d and d != last:
            rows.append({"bar": i, "date": dt, "direction": "up" if d > 0 else "down", "close": r.close,
                         "broke": hi.iloc[i] if d > 0 else lo.iloc[i]})
            last = d
    return pd.DataFrame(rows)
