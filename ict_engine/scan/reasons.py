"""Scrutinise one candidate: the reasons FOR and AGAINST the entry, and a conviction label.

Every reason is a fact computed by the engine (no opinions). The walk-forward evidence quoted
comes from reports/walkforward (Feb–Nov 2026, 60m proxy, after Indian delivery costs):
  A-like setups (confluence in OTE + daily up)   +0.07R/trade (50 trades)
  B-like setups                                  −0.38R/trade
  trades on days the market filter blocked       −0.29R/trade
Conviction
  STRONG    market allows longs AND A-like AND Time Machine avg R (filled) > 0 AND costs ≤ 0.15R
  MODERATE  (A-like OR Time Machine avg R > 0) AND at most 2 reasons against
  WEAK      everything else
"""
from __future__ import annotations

import numpy as np


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and np.isnan(x))


def scrutinise(r: dict, market_ok: bool, cost_pct: float) -> dict:
    pro, con = [], []
    entry, stop = r.get("entry"), r.get("stop")
    risk = entry - stop if _ok(entry) and _ok(stop) else np.nan
    cost_r = cost_pct / 100 * entry / risk if _ok(risk) and risk > 0 else np.nan

    # market
    if market_ok:
        pro.append("Market filter allows longs (NIFTY 500 structure, breadth and VIX OK).")
    else:
        con.append("Market filter blocks longs today; in the walk-forward such trades averaged −0.29R.")
    # setup quality
    a_like = bool(r.get("has_confluence")) and r.get("bias") == "up"
    if a_like:
        pro.append("A-like: FVG/OB confluence inside the OTE band AND daily structure up "
                   "(the only positive group in the walk-forward, +0.07R/trade, 50 trades: promising, not proven).")
    else:
        miss = [x for x, ok in (("no FVG/OB inside the OTE band", bool(r.get("has_confluence"))),
                                (f"daily structure {r.get('bias')}, not up", r.get("bias") == "up")) if not ok]
        con.append("B-like (" + ", ".join(miss) + "); B-like setups averaged −0.38R in the walk-forward.")
    if r.get("base_rules") is False:
        con.append("Wide-mode only: fails at least one base daily filter (discount, zone proximity or relative strength).")
    # 45m mechanics
    st = r.get("sweep_type")
    if st:
        lvl = "intermediate/long-term" if str(st)[:1] in ("I", "L") else "short-term"
        (pro if lvl != "short-term" else con).append(
            f"Sell-side sweep of a {lvl} low ({st} {r.get('sweep_level', np.nan):,.2f}); "
            + ("larger liquidity taken." if lvl != "short-term" else "only minor liquidity taken."))
    if _ok(r.get("mss_level")):
        pro.append(f"Market structure shift: a displacement candle CLOSED above {r['mss_level']:,.2f} after the sweep.")
    conf = r.get("confluence") or []
    if conf:
        pro.append("Inside the OTE band: " + ", ".join(f"{z[0]} {z[1]:,.2f}–{z[2]:,.2f}" for z in conf) + ".")
    # daily context
    eq = r.get("eq")
    if _ok(eq) and _ok(r.get("last_close")):
        pct = (r["last_close"] / eq - 1) * 100
        (pro if pct < 0 else con).append(f"Daily dealing range: price {abs(pct):.1f} % {'below' if pct < 0 else 'above'} "
                                         f"equilibrium {eq:,.2f} ({'discount' if pct < 0 else 'premium'}).")
    if _ok(r.get("zone_atr")) and r.get("zone"):
        za = r["zone_atr"]
        (pro if za <= 1 else con).append(f"Nearest daily support zone: {r['zone']} ({za:.1f} ATR away).")
    if _ok(r.get("room_atr")) and np.isfinite(r["room_atr"]):
        (pro if r["room_atr"] >= 2 else con).append(f"Room to the next daily buy-side liquidity: {r['room_atr']:.1f} ATR.")
    if _ok(r.get("rs_pct")):
        rs = r["rs_pct"]
        if rs >= 70:
            pro.append(f"Relative strength vs NIFTY 500 in the top {100 - rs:.0f} % of candidates.")
        elif rs < 50:
            con.append(f"Relative strength weak (percentile {rs:.0f}).")
    # plan economics
    rr = r.get("rr_t2")
    if _ok(rr):
        (pro if rr >= 2 else con).append(f"Reward to T2 is {rr:.2f}R.")
    else:
        con.append("No open buy-side liquidity above the leg for T2: only T1 is defined.")
    if _ok(cost_r):
        if cost_r <= 0.12:
            pro.append(f"Costs are small relative to the stop ({cost_r:.2f}R per round trip).")
        elif cost_r > 0.2:
            con.append(f"Tight stop: costs take {cost_r:.2f}R per round trip.")
    # Time Machine
    tm = r.get("tm_avg_R_filled")
    if _ok(tm):
        txt = (f"Time Machine ({r.get('tm_fill_pct', np.nan):.0f} % fill, {r.get('tm_win_pct', np.nan):.0f} % wins when "
               f"filled): average {tm:+.2f}R after costs.")
        (pro if tm > 0 else con).append(txt)
    # conviction
    strong = market_ok and a_like and _ok(tm) and tm > 0 and (_ok(cost_r) and cost_r <= 0.15)
    moderate = (a_like or (_ok(tm) and tm > 0)) and len(con) <= 2
    label = "STRONG" if strong else "MODERATE" if moderate else "WEAK"
    return {"conviction": label, "pros": pro, "cons": con, "a_like": a_like, "cost_R": cost_r}
