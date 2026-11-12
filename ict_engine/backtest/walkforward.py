"""Walk-forward validation of the scanner. Nothing here can see the future.

Process for every trading day D in [start, end]:
  1. Stages 0-2 use only daily bars up to D's close (computed point-in-time: swings, FVGs and
     order blocks are detected once on the full history and then read "as of D", which the
     no-lookahead tests prove is identical to recomputing on the truncated data).
  2. Stage 3 runs on intraday bars up to D's close for each stage-2 survivor.
  3. An actionable setup (waiting / in_zone) places a limit order at the 70.5% level for the next
     ``order_valid_sessions`` sessions. One order per (symbol, MSS); repeats on later days are ignored.
  4. The order is simulated bar by bar on the following intraday bars:
       fill   : first bar whose low ≤ entry (at the open if it gaps below the entry)
       cancel : a low below the leg low before the fill, or the order expires
       manage : stop first if stop and target fall in the same bar; exit at the open on a gap
                through the stop; 50% off at T1 then stop to breakeven; the rest to T2;
                time stop after ``hold_days``
       costs  : Indian delivery costs from config.yaml (costs:) subtracted, expressed in R
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ict_engine.detectors import basic as B
from ict_engine.detectors.swings import swing_table, swings_as_of
from ict_engine.scan.ote import ACTIONABLE, find_ote_setup
from ict_engine.scan.stages import CR, structure_bias

# ----------------------------------------------------------------------------- stage 0 / 1 (all dates)


def stage0_series(indices: dict, panel: pd.DataFrame, dates, cfg) -> pd.DataFrame:
    c = cfg["scan"]["stage0"]
    n500 = indices.get("nifty500") if indices.get("nifty500") is not None else indices.get("nifty50")
    sw = swing_table(n500, cfg) if n500 is not None else None
    p = panel.sort_values(["symbol", "date"])
    sma = p.groupby("symbol")["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
    above = (p.close > sma).where(sma.notna())
    breadth = above.groupby(p.date).mean() * 100
    vix = indices.get("vix")
    rows = []
    for d in dates:
        bias, zone = "range", "n/a"
        if sw is not None:
            t = swings_as_of(sw, d)
            if len(t):
                bias = structure_bias(t)
                rng = B.dealing_range(t[t.level >= 2])
                if rng:
                    px = n500.close[n500.index <= d]
                    zone = "premium" if len(px) and px.iloc[-1] > rng["eq"] else "discount"
        b = float(breadth.get(d, np.nan))
        v = float(vix.close[vix.index <= d].iloc[-1]) if vix is not None and (vix.index <= d).any() else np.nan
        blocks = []
        if c.get("block_on_down_bias", True) and bias == "down":
            blocks.append("down")
        if b == b and b < c["breadth_min_pct"]:
            blocks.append("breadth")
        if v == v and v > c["vix_max"]:
            blocks.append("vix")
        rows.append({"date": d, "mkt_bias": bias, "mkt_zone": zone, "breadth": b, "vix": v,
                     "market_ok": not blocks, "market_blocks": ",".join(blocks)})
    return pd.DataFrame(rows).set_index("date")


def stage1_series(panel: pd.DataFrame, cfg, exclude=frozenset()) -> pd.DataFrame:
    """Stage-1 metrics for every (date, symbol), computed once with rolling windows."""
    c = cfg["scan"]["stage1"]
    p = panel.sort_values(["symbol", "date"]).copy()
    g = p.groupby("symbol")
    prev = g["close"].shift(1)
    p["tr"] = np.maximum(p.high - p.low, np.maximum((p.high - prev).abs(), (p.low - prev).abs())).fillna(p.high - p.low)
    to = p["turnover"].where(p["turnover"] > 0, p.close * p.volume)
    p["to"] = to
    p["atr14"] = g["tr"].transform(lambda s: s.rolling(14, min_periods=14).mean())
    p["to20"] = g["to"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    p["nbars"] = g.cumcount() + 1
    ok = ((p.nbars >= c["min_history_bars"]) & (p.close >= c["min_price"]) & (p.to20 / CR >= c["min_turnover_cr"])
          & (p.atr14 / p.close * 100).between(c["atr_pct_min"], c["atr_pct_max"]) & ~p.symbol.isin(list(exclude)))
    p["s1"] = ok
    return p[["date", "symbol", "close", "s1"]]


# ----------------------------------------------------------------------------- stage 2 (point in time)


def stage2_series(sym: str, d: pd.DataFrame, dates, cfg) -> pd.DataFrame:
    """Daily ICT context for one symbol on each requested date, using only data up to that date."""
    c = cfg["scan"]["stage2"]
    d = d.sort_index()
    if len(d) < 30:
        return pd.DataFrame()
    sw = swing_table(d, cfg)
    f = B.fvgs(d, cfg["pd_arrays"].get("fvg_min_size_atr", 0.1))
    ob = B.order_blocks(d, cfg["pd_arrays"]["displacement_atr_mult"], cfg["pd_arrays"]["ob_lookback_bars"])
    atr = B.atr(d)
    ret = d.close.pct_change(c["rs_lookback"]) * 100
    pos = {ts: i for i, ts in enumerate(d.index)}
    rows = []
    for D in dates:
        i = pos.get(D)
        if i is None:
            continue
        t = swings_as_of(sw, D)
        if t.empty:
            continue
        last, a = float(d.close.iloc[i]), float(atr.iloc[i])
        bias = structure_bias(t)
        rng = B.dealing_range(t[t.level >= 2])
        eq = rng["eq"] if rng else np.nan
        zones = []
        if len(f):
            for r in f[(f.side == "bull") & (f.bar + 1 <= i) & (f.filled_bar.isna() | (f.filled_bar > i))].itertuples():
                zones.append((r.bottom, r.top))
        if len(ob):
            for r in ob[(ob.side == "bull") & (ob.displacement_bar <= i) & (ob.breaker_bar.isna() | (ob.breaker_bar > i))].itertuples():
                zones.append((r.bottom, r.top))
        for r in t[(t.side == "low") & t.unbroken & (t.level >= 2)].itertuples():
            zones.append((r.price, r.price))
        dist = min((0.0 if lo <= last <= hi else (last - hi if last > hi else lo - last)) for lo, hi in zones) if zones else np.inf
        above = t[(t.side == "high") & t.unbroken & (t.level >= 2) & (t.price > last)]
        bsl = float(above.price.min()) if len(above) else np.nan
        rows.append({
            "date": D, "symbol": sym, "bias": bias, "discount": bool(rng) and last < eq, "eq": eq,
            "range_low": rng["low"] if rng else np.nan, "range_high": rng["high"] if rng else np.nan,
            "zone_atr": dist / a if a else np.inf, "room_atr": (bsl - last) / a if bsl == bsl and a else np.inf,
            "ret_rs": float(ret.iloc[i]), "daily_bsl_levels": sorted(above.price.tolist())[:5],
        })
    return pd.DataFrame(rows)


ABLATIONS = {
    "base": {},
    "no_market_filter": {"market": False},
    "no_rs_filter": {"rs": False},
    "no_zone_filter": {"zone": False},
    "no_room_filter": {"room": False},
    "require_confluence": {"confluence": True},
}


def apply_stage2(ctx: pd.DataFrame, bench_ret: pd.Series, cfg, rules: dict) -> pd.Series:
    """Boolean mask of stage-2 survivors under an ablation's rules."""
    c = cfg["scan"]["stage2"]
    ok = ctx.bias.isin(c["require_bias"])
    if c["require_discount"] and rules.get("discount", True):
        ok &= ctx.discount
    if rules.get("zone", True):
        ok &= ctx.zone_atr <= c["zone_proximity_atr"]
    if rules.get("room", True):
        ok &= ctx.room_atr >= c["min_room_atr"]
    if rules.get("rs", True):
        rs = ctx.ret_rs - ctx.date.map(bench_ret).fillna(0)
        pct = rs.where(ok).groupby(ctx.date).rank(pct=True) * 100
        ok &= pct >= c["rs_min_pct"]
    return ok


# ----------------------------------------------------------------------------- stage 3 + trade simulation

@dataclass
class SimCfg:
    order_valid_sessions: int = 2
    hold_days: int = 15
    partial_at_t1: float = 0.5
    cost_pct_round_trip: float = 0.0


def cost_pct(cfg) -> float:
    """Round-trip delivery cost as % of price (buy + sell)."""
    k = cfg["costs"]
    exch = 2 * k["exchange_txn_pct"] + 2 * k["sebi_fee_pct"]
    gst = exch * k["gst_pct_on_charges"] / 100
    return 2 * k["stt_pct"] + k["stamp_duty_buy_pct"] + exch + gst + 2 * k["slippage_pct"] + 2 * k["brokerage_pct"]


def simulate(bars: pd.DataFrame, start_i: int, setup: dict, sim: SimCfg, bars_per_day: int) -> dict:
    """Simulate one limit order from bar ``start_i`` (the first bar after the scan)."""
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    entry, stop, t1, t2, leg_low = setup["entry"], setup["stop"], setup["t1"], setup["t2"], setup["leg_low"]
    risk = entry - stop
    days = bars.index.normalize()
    start_day = days[start_i] if start_i < len(bars) else None
    out = {"result": "no fill", "fill_time": pd.NaT, "exit_time": pd.NaT, "R_gross": np.nan, "fill": np.nan}
    if start_day is None:
        out["result"] = "no data after scan"
        return out
    uniq = pd.Index(days[start_i:]).unique()
    last_day = uniq[min(sim.order_valid_sessions, len(uniq)) - 1]
    fill_i, fill_px = None, None
    for i in range(start_i, len(bars)):
        if days[i] > last_day:
            break
        # a resting buy limit fills on the first touch (at the open if price gaps below it);
        # if that same move takes the sweep low, the stop check on the fill bar handles it
        if l[i] <= entry:
            fill_i, fill_px = i, min(o[i], entry)
            break
    if fill_i is None:
        return out
    out["fill_time"], out["fill"] = bars.index[fill_i], fill_px
    risk = fill_px - stop
    if risk <= 0:
        out["result"] = "gap below stop at fill"
        out["R_gross"] = -1.0
        out["exit_time"] = bars.index[fill_i]
        return out
    cur_stop, half_done, realised, size = stop, False, 0.0, 1.0
    limit_i = fill_i + sim.hold_days * bars_per_day
    for i in range(fill_i, min(len(bars), limit_i)):
        if i > fill_i and o[i] <= cur_stop:                     # gap through the stop
            realised += size * (o[i] - fill_px) / risk
            out.update(result="stop (gap)" if not half_done else "T1 then BE (gap)", exit_time=bars.index[i])
            out["R_gross"] = realised
            return out
        if l[i] <= cur_stop:
            realised += size * (cur_stop - fill_px) / risk
            out.update(result="stop" if not half_done else "T1 then breakeven", exit_time=bars.index[i])
            out["R_gross"] = realised
            return out
        if not half_done and h[i] >= t1:
            part = sim.partial_at_t1 if t2 == t2 and t2 > t1 else 1.0
            realised += part * (t1 - fill_px) / risk
            size -= part
            half_done, cur_stop = True, fill_px
            if size <= 1e-9:
                out.update(result="T1", exit_time=bars.index[i], R_gross=realised)
                return out
        if half_done and t2 == t2 and h[i] >= t2:
            realised += size * (t2 - fill_px) / risk
            out.update(result="T1 + T2", exit_time=bars.index[i], R_gross=realised)
            return out
    end_i = min(len(bars), limit_i) - 1
    realised += size * (c[end_i] - fill_px) / risk
    still_open = limit_i > len(bars)
    out.update(result="open at end of data" if still_open else "time stop", exit_time=bars.index[end_i], R_gross=realised)
    return out


def symbol_trades(sym: str, bars: pd.DataFrame, scan_days: list, ctx_by_day: dict, cfg, sim: SimCfg,
                  bars_per_day: int, window: int) -> list[dict]:
    """Stage 3 on each scan day for one symbol, then simulate each new order."""
    trades = []
    if bars is None or bars.empty:
        return trades
    ends = bars.index.normalize()
    for D in sorted(scan_days):
        upto = int(np.searchsorted(ends.values, np.datetime64(D + pd.Timedelta(days=1)), side="left"))
        if upto < 40:
            continue
        sub = bars.iloc[max(0, upto - window):upto]
        ctx = ctx_by_day.get(D, {})
        try:
            r = find_ote_setup(sub, cfg, ctx.get("daily_bsl_levels"))
        except Exception:
            continue
        if r.get("state") not in ACTIONABLE or r.get("reason"):
            continue
        key = pd.Timestamp(r["mss_time"])
        res = simulate(bars, upto, r, sim, bars_per_day)
        cost_r = sim.cost_pct_round_trip / 100 * r["entry"] / r["risk"] if r["risk"] > 0 else np.nan
        trades.append({"symbol": sym, "scan_date": D, "state_at_scan": r["state"], "mss_time": key,
                       "entry": r["entry"], "stop": r["stop"], "t1": r["t1"], "t2": r["t2"],
                       "rr_t2": r["rr_t2"], "has_confluence": r["has_confluence"],
                       "bias": ctx.get("bias"), "market_ok": ctx.get("market_ok"), **res,
                       "cost_R": cost_r if res["result"] not in ("no fill", "no data after scan") else 0.0})
    return trades


def _symbol_trades_star(args):
    return symbol_trades(*args)


def run_trades(intraday: dict, plan: pd.DataFrame, cfg, sim: SimCfg, bars_per_day: int, window: int,
               workers: int = 4) -> pd.DataFrame:
    """plan: rows (date, symbol, …context…) for every stage-2 survivor under any ablation."""
    jobs = []
    for sym, g in plan.groupby("symbol"):
        ctx = {r["date"]: r for r in g.to_dict("records")}
        jobs.append((sym, intraday.get(sym), list(ctx), ctx, cfg, sim, bars_per_day, window))
    if workers > 1 and len(jobs) > 4:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(_symbol_trades_star, jobs, chunksize=4))
    else:
        res = [_symbol_trades_star(j) for j in jobs]
    rows = [t for r in res for t in r]
    df = pd.DataFrame(rows)
    if len(df):
        df["R"] = df["R_gross"] - df["cost_R"].fillna(0)
    return df


# ----------------------------------------------------------------------------- metrics


def select_orders(occ: pd.DataFrame, allowed: set) -> pd.DataFrame:
    """Orders a trader following one rule set would actually have placed.

    ``occ`` holds every evening's actionable setup (symbol, scan_date, mss_time, result, …).
    Keep an occurrence only if its (symbol, scan_date) passed the rule set's stages 0-2, and the
    same setup (symbol, mss_time) has not already been filled by an earlier order.
    """
    if occ.empty:
        return occ
    occ = occ[[k in allowed for k in zip(occ.symbol, occ.scan_date)]].sort_values("scan_date")
    keep, filled = [], set()
    for idx, r in zip(occ.index, occ.itertuples()):
        key = (r.symbol, r.mss_time)
        if key in filled:
            continue
        keep.append(idx)
        if r.result not in ("no fill", "no data after scan"):
            filled.add(key)
    return occ.loc[keep]


def metrics(t: pd.DataFrame) -> dict:
    traded = t[t["R"].notna()] if len(t) else t
    n = len(traded)
    if n == 0:
        return {"signals": len(t), "trades": 0}
    r = traded["R"]
    eq = r.cumsum()
    dd = float((eq - eq.cummax()).min())
    streak = best = 0
    for v in r:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    wins, losses = r[r > 0], r[r < 0]
    return {"signals": len(t), "fill_rate_pct": round(n / len(t) * 100, 1), "trades": n,
            "win_rate_pct": round((r > 0).mean() * 100, 1), "avg_R": round(r.mean(), 3),
            "total_R": round(r.sum(), 2), "profit_factor": round(wins.sum() / -losses.sum(), 2) if len(losses) else np.inf,
            "max_drawdown_R": round(dd, 2), "max_losing_streak": best,
            "avg_cost_R": round(traded["cost_R"].mean(), 3)}
