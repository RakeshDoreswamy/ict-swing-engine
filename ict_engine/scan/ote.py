"""Stage 3: the 45-minute OTE trigger (long side; shorts mirror it).

Exact rule
----------
1. A bullish MSS on 45m within the last ``max_setup_age`` bars (close above the last confirmed STH,
   body > MSS × ATR, prior swing lows falling: ict_engine.detectors.basic.mss_events).
2. A sell-side sweep (wick below a confirmed swing low, close back above) within ``sweep_lookback``
   bars BEFORE the MSS.
3. OTE leg: leg low = lowest low from the sweep bar to the MSS bar; leg high = highest high from the
   MSS bar onwards, and it must already be followed by at least one bar (a pullback has begun).
4. OTE band = leg high − [0.62, 0.79] × leg; planned entry = 0.705 (limit).
5. Confluence: a bullish FVG or order block created inside the leg (sweep bar → leg high bar) that
   overlaps the OTE band.
6. State, from the bars after the leg high:
     invalid   : a low below the leg low (the sweep extreme was taken)
     triggered : a low reached the 70.5% entry (already filled: not a new signal)
     in_zone   : a low reached the 62% line but not 70.5%
     waiting   : price still above the band
     stale     : waiting, but more than ``stale_after_high`` bars since the leg high
7. Plan: stop = leg low − buffer × ATR (at least min_stop × ATR below the entry); T1 = leg high;
   T2 = the nearest open buy-side liquidity above the leg high (45m ITH/LTH not yet taken, or the
   daily levels passed in). R:R to T2 must be ≥ min_rr_t2.
Everything uses closed bars only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict_engine.detectors import basic as B
from ict_engine.detectors.swings import swing_table

ACTIONABLE = ("waiting", "in_zone")


def find_ote_setup(m45: pd.DataFrame, cfg: dict, daily_bsl: list | None = None) -> dict:
    c = cfg["scan"]["stage3"]
    n = len(m45)
    res = {"state": "none", "reason": "no bullish MSS after a sweep in the last "
                                      f"{c['max_setup_age']} bars"}
    if n < 40:
        res["reason"] = "not enough 45m bars"
        return res
    sw = swing_table(m45, cfg)
    sweeps = B.sweeps(m45, sw)
    mss = B.mss_events(m45, sw, cfg["confirmation"]["mss_displacement_atr_mult"])
    if mss is None or mss.empty or sweeps is None or sweeps.empty:
        return res
    atr = B.atr(m45)
    a_now = float(atr.iloc[-1])
    h, l, cl = m45.high.to_numpy(), m45.low.to_numpy(), m45.close.to_numpy()
    fv = B.fvgs(m45, 0.0)
    obs = B.order_blocks(m45, cfg["pd_arrays"]["displacement_atr_mult"], cfg["pd_arrays"]["ob_lookback_bars"])
    bull_mss = mss[(mss.side == "bull") & (mss.bar >= n - c["max_setup_age"])].sort_values("bar", ascending=False)
    first_reason = None
    for m in bull_mss.itertuples():
        prior = sweeps[(sweeps.side == "sell-side") & (sweeps.bar < m.bar) & (sweeps.bar >= m.bar - c["sweep_lookback"])]
        if prior.empty:
            first_reason = first_reason or "MSS without a sell-side sweep before it"
            continue
        s = prior.iloc[-1]
        sb, mb = int(s.bar), int(m.bar)
        low_bar = sb + int(np.argmin(l[sb:mb + 1]))
        leg_low = float(l[low_bar])
        hb = mb + int(np.argmax(h[mb:n]))
        leg_high = float(h[hb])
        if hb >= n - 1:
            first_reason = first_reason or "leg still making new highs (no pullback yet)"
            continue
        rng = leg_high - leg_low
        if rng <= 0:
            continue
        o62, o79 = leg_high - c["ote_low"] * rng, leg_high - c["ote_high"] * rng
        entry = leg_high - c["ote_entry"] * rng
        pb_low = float(l[hb + 1:n].min())
        fill = np.nonzero(l[hb + 1:n] <= entry)[0]
        if pb_low < leg_low:
            state = "invalid"
        elif fill.size:
            state = "triggered"
        elif pb_low <= o62:
            state = "in_zone"
        else:
            state = "waiting" if (n - 1 - hb) <= c["stale_after_high"] else "stale"
        # confluence: bullish FVG / OB from inside the leg overlapping the OTE band
        conf = []
        if len(fv):
            for z in fv[(fv.side == "bull") & (fv.bar >= sb) & (fv.bar <= hb)].itertuples():
                if z.bottom <= o62 and z.top >= o79:
                    conf.append(("FVG", float(z.bottom), float(z.top), int(z.bar)))
        if len(obs):
            for z in obs[(obs.side == "bull") & (obs.displacement_bar >= sb) & (obs.displacement_bar <= hb)].itertuples():
                if z.bottom <= o62 and z.top >= o79:
                    conf.append(("OB", float(z.bottom), float(z.top), int(z.bar)))
        stop = min(leg_low - c["stop_buffer_atr"] * a_now, entry - c["min_stop_atr"] * a_now)
        risk = entry - stop
        # T2: nearest open buy-side liquidity above the leg high
        cands = [p for p in sw[(sw.side == "high") & sw.unbroken & (sw.level >= 2)].price if p > leg_high]
        cands += [p for p in (daily_bsl or []) if p > leg_high]
        t2 = float(min(cands)) if cands else np.nan
        rr1 = (leg_high - entry) / risk if risk > 0 else np.nan
        rr2 = (t2 - entry) / risk if risk > 0 and t2 == t2 else np.nan
        res = {
            "state": state, "sweep_bar": sb, "sweep_time": m45.index[sb], "sweep_type": s.swing_type,
            "sweep_level": float(s.level), "mss_bar": mb, "mss_time": m45.index[mb], "mss_level": float(m.level),
            "leg_low": leg_low, "leg_low_bar": low_bar, "leg_high": leg_high, "leg_high_bar": hb,
            "ote_62": o62, "ote_79": o79, "entry": entry, "stop": stop, "risk": risk,
            "t1": leg_high, "t2": t2, "rr_t1": rr1, "rr_t2": rr2, "confluence": conf,
            "has_confluence": bool(conf), "atr45": a_now, "last_close": float(cl[-1]),
            "dist_to_entry_atr": (float(cl[-1]) - entry) / a_now if a_now else np.nan,
            "bars_since_high": n - 1 - hb, "reason": "",
        }
        if state not in ACTIONABLE:
            res["reason"] = {"invalid": "pullback took the sweep low", "triggered": "entry already filled",
                             "stale": "pullback too slow (stale)"}[state]
        elif not (rr2 == rr2) or rr2 < c["min_rr_t2"]:
            res["reason"] = (f"R:R to T2 {rr2:.2f} < {c['min_rr_t2']}" if rr2 == rr2
                             else "no open buy-side liquidity above the leg for T2")
        return res
    if first_reason:
        res["reason"] = first_reason
    return res


def stage3_symbol(sym: str, m45: pd.DataFrame, cfg: dict, daily_bsl: list | None) -> dict:
    try:
        r = find_ote_setup(m45, cfg, daily_bsl)
    except Exception as e:
        r = {"state": "error", "reason": f"error: {type(e).__name__}: {e}"}
    r["symbol"] = sym
    r["pass"] = r.get("state") in ACTIONABLE and not r.get("reason")
    return r
