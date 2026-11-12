"""Scanner stages 0-2 (daily). Each stage returns a DataFrame with a ``reason`` column for
every symbol it rejects, so funnel.csv explains every drop.

Stage 0  market regime    NIFTY 500 structure, breadth, India VIX -> allowed side
Stage 1  universe filter  liquidity / price / volatility / history / exclusions / earnings (vectorised)
Stage 2  daily ICT        bias, discount, near a PD array, room to the next buy-side liquidity, RS
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict_engine.detectors import basic as B
from ict_engine.detectors.swings import swing_table

CR = 1e7  # rupees per crore


# --------------------------------------------------------------------------- helpers
def structure_bias(sw: pd.DataFrame) -> str:
    """up if the last two ITH/LTH AND ITL/LTL rise, down if both fall, else range."""
    hi = sw[(sw.side == "high") & (sw.level >= 2)].sort_values("bar")
    lo = sw[(sw.side == "low") & (sw.level >= 2)].sort_values("bar")
    if len(hi) < 2 or len(lo) < 2:
        return "range"
    hh = hi.price.iloc[-1] > hi.price.iloc[-2]
    hl = lo.price.iloc[-1] > lo.price.iloc[-2]
    return "up" if hh and hl else "down" if (not hh and not hl) else "range"


def panel_to_frames(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for sym, g in panel.groupby("symbol", sort=False):
        out[sym] = g.set_index("date").sort_index()[["open", "high", "low", "close", "volume", "turnover"]]
    return out


# --------------------------------------------------------------------------- stage 0
def stage0_market(indices: dict[str, pd.DataFrame], panel: pd.DataFrame, cfg: dict) -> dict:
    c = cfg["scan"]["stage0"]
    out = {"allowed_side": "long", "checks": {}, "sentence": ""}
    n500 = indices.get("nifty500")
    if n500 is None or n500.empty:
        n500 = indices.get("nifty50")
    bias, zone, eq = "range", "n/a", np.nan
    if n500 is not None and len(n500) > 30:
        sw = swing_table(n500, cfg)
        bias = structure_bias(sw)
        rng = B.dealing_range(sw[sw.level >= 2])
        if rng:
            eq = rng["eq"]
            zone = "premium" if n500.close.iloc[-1] > eq else "discount"
    # breadth from the universe panel: % above 50-day SMA, advance/decline on the last day
    p = panel.sort_values(["symbol", "date"])
    p["sma50"] = p.groupby("symbol")["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
    p["prev"] = p.groupby("symbol")["close"].shift(1)
    last = p[p.date == p.date.max()]
    breadth = float((last.close > last.sma50).sum() / max(last.sma50.notna().sum(), 1) * 100)
    adv, dec = int((last.close > last.prev).sum()), int((last.close < last.prev).sum())
    vix_df = indices.get("vix")
    vix = float(vix_df.close.iloc[-1]) if vix_df is not None and len(vix_df) else np.nan
    checks = {
        "nifty500_bias": bias, "nifty500_zone": zone, "breadth_pct_above_50sma": round(breadth, 1),
        "adv_dec": f"{adv}/{dec}", "india_vix": None if np.isnan(vix) else round(vix, 2),
    }
    blocks = []
    if c.get("block_on_down_bias", True) and bias == "down":
        blocks.append("NIFTY 500 daily structure is down")
    if breadth < c["breadth_min_pct"]:
        blocks.append(f"breadth {breadth:.0f}% < {c['breadth_min_pct']}%")
    if not np.isnan(vix) and vix > c["vix_max"]:
        blocks.append(f"India VIX {vix:.1f} > {c['vix_max']}")
    out["checks"] = checks
    out["blocks"] = blocks
    out["allowed_side"] = "none" if blocks else cfg["scan"].get("side", "long")
    out["sentence"] = (f"NIFTY 500 structure {bias}, price in {zone}; {breadth:.0f}% of stocks above their 50-day SMA "
                       f"(A/D {adv}/{dec})" + (f"; India VIX {vix:.1f}" if not np.isnan(vix) else "") + ". "
                       + ("New longs allowed." if not blocks else "No new longs: " + "; ".join(blocks) + "."))
    return out


# --------------------------------------------------------------------------- stage 1
def stage1_universe(panel: pd.DataFrame, cfg: dict, exclude: set | None = None,
                    events: pd.DataFrame | None = None, as_of=None) -> pd.DataFrame:
    """Vectorised daily filter over the whole universe. Returns one row per symbol."""
    c = cfg["scan"]["stage1"]
    p = panel.sort_values(["symbol", "date"]).copy()
    as_of = pd.Timestamp(as_of) if as_of is not None else p.date.max()
    p = p[p.date <= as_of]
    g = p.groupby("symbol")
    prev_close = g["close"].shift(1)
    tr = np.maximum(p.high - p.low, np.maximum((p.high - prev_close).abs(), (p.low - prev_close).abs()))
    p["tr"] = tr.fillna(p.high - p.low)
    turnover = p["turnover"].where(p["turnover"].notna() & (p["turnover"] > 0), p.close * p.volume)
    p["to"] = turnover
    p["atr14"] = p.groupby("symbol")["tr"].transform(lambda s: s.rolling(14, min_periods=14).mean())
    p["to20"] = p.groupby("symbol")["to"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    last = p.groupby("symbol").tail(1).set_index("symbol")
    hist = g.size()
    df = pd.DataFrame({
        "last_date": last.date, "close": last.close, "turnover_cr": last.to20 / CR,
        "atr_pct": last.atr14 / last.close * 100, "history": hist.reindex(last.index),
    })
    reasons = pd.Series("", index=df.index, dtype=object)

    def rej(mask, text):
        nonlocal reasons
        m = mask & (reasons == "")
        reasons[m] = text

    rej(df.last_date < as_of, "did not trade on scan date")
    rej(df.history < c["min_history_bars"], f"history < {c['min_history_bars']} bars")
    rej(df.close < c["min_price"], f"price < {c['min_price']}")
    rej(df.turnover_cr < c["min_turnover_cr"], f"20d turnover < {c['min_turnover_cr']} Cr")
    rej((df.atr_pct < c["atr_pct_min"]) | (df.atr_pct > c["atr_pct_max"]),
        f"ATR% outside {c['atr_pct_min']}-{c['atr_pct_max']}")
    if exclude:
        rej(df.index.isin(list(exclude)), "in exclude list (ASM/GSM/T2T)")
    if events is not None and len(events):
        ev = events.copy()
        ev["date"] = pd.to_datetime(ev["date"])
        horizon = as_of + pd.Timedelta(days=int(c.get("holding_days", 15) * 1.4))
        soon = ev[(ev.date >= as_of) & (ev.date <= horizon)]
        syms = set(soon.symbol.astype(str))
        if "ALL" in syms:
            reasons[reasons == ""] = "market-wide event in holding window"
        rej(df.index.isin(list(syms)), "earnings/event in holding window")
    df["reason"] = reasons
    df["pass"] = df.reason == ""
    return df.sort_values("turnover_cr", ascending=False)


# --------------------------------------------------------------------------- stage 2
def stage2_symbol(sym: str, d: pd.DataFrame, cfg: dict, side: str = "long") -> dict:
    """Daily ICT context for one symbol (runs in a worker process)."""
    c = cfg["scan"]["stage2"]
    out = {"symbol": sym, "pass": False, "reason": ""}
    try:
        sw = swing_table(d, cfg)
        bias = structure_bias(sw)
        last = float(d.close.iloc[-1])
        atr = float(B.atr(d).iloc[-1])
        rng = B.dealing_range(sw[sw.level >= 2])
        eq = rng["eq"] if rng else np.nan
        disc = bool(rng) and last < eq
        # nearest daily PD arrays below/at price (for longs): unfilled bull FVG, unbroken bull OB, open ITL/LTL
        zones = []
        f = B.fvgs(d, cfg["pd_arrays"].get("fvg_min_size_atr", 0.1))
        if len(f):
            for r in f[(f.side == "bull") & f.filled_bar.isna()].itertuples():
                zones.append(("daily bull FVG", r.bottom, r.top))
        ob = B.order_blocks(d, cfg["pd_arrays"]["displacement_atr_mult"], cfg["pd_arrays"]["ob_lookback_bars"])
        if len(ob):
            for r in ob[(ob.side == "bull") & ob.breaker_bar.isna()].itertuples():
                zones.append(("daily bull OB", r.bottom, r.top))
        for r in sw[(sw.side == "low") & sw.unbroken & (sw.level >= 2)].itertuples():
            zones.append((f"open {r.type}", r.price, r.price))
        best, best_d = None, np.inf
        for name, lo, hi in zones:
            dist = 0.0 if lo <= last <= hi else (last - hi if last > hi else lo - last)
            if dist < best_d:
                best, best_d = (name, lo, hi), dist
        zone_atr = best_d / atr if atr else np.inf
        # room to the next open buy-side liquidity (intermediate+ swing highs not yet taken)
        above = sw[(sw.side == "high") & sw.unbroken & (sw.price > last) & (sw.level >= 2)]
        bsl = float(above.price.min()) if len(above) else np.nan
        room_atr = (bsl - last) / atr if not np.isnan(bsl) and atr else np.inf
        ret = d.close.pct_change(c["rs_lookback"]).iloc[-1] * 100
        out.update({
            "bias": bias, "close": last, "atr": atr, "eq": eq, "range_low": rng["low"] if rng else np.nan,
            "range_high": rng["high"] if rng else np.nan, "discount": disc,
            "zone": best[0] if best else "", "zone_low": best[1] if best else np.nan,
            "zone_high": best[2] if best else np.nan, "zone_atr": zone_atr,
            "bsl_above": bsl, "room_atr": room_atr, "ret_rs": ret,
            "daily_bsl_levels": sorted(above.price.tolist())[:5],
        })
        if bias not in c["require_bias"]:
            out["reason"] = f"daily bias {bias}"
        elif c["require_discount"] and not disc:
            out["reason"] = "not in daily discount"
        elif zone_atr > c["zone_proximity_atr"]:
            out["reason"] = f"no daily PD array within {c['zone_proximity_atr']} ATR"
        elif room_atr < c["min_room_atr"]:
            out["reason"] = f"next buy-side liquidity only {room_atr:.1f} ATR away"
        else:
            out["pass"] = True
    except Exception as e:  # keep the scan going; record why
        out["reason"] = f"error: {type(e).__name__}: {e}"
    return out


def stage2_rs(df: pd.DataFrame, bench_ret: float, cfg: dict) -> pd.DataFrame:
    """Relative strength vs NIFTY 500, as a percentile among stage-2 candidates."""
    c = cfg["scan"]["stage2"]
    df = df.copy()
    df["rs"] = df["ret_rs"] - (bench_ret if bench_ret == bench_ret else 0.0)
    df["rs_pct"] = df["rs"].rank(pct=True) * 100
    weak = df["pass"] & (df["rs_pct"] < c["rs_min_pct"])
    df.loc[weak, "reason"] = df.loc[weak, "rs_pct"].map(lambda v: f"relative strength {v:.0f} pct < {c['rs_min_pct']}")
    df.loc[weak, "pass"] = False
    return df
