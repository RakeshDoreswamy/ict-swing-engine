"""Run every ICT concept on one instrument and collect the results.

Used by scripts/annotate_chart.py to draw the practice images, and handy on its own:

    from ict_engine.analysis.practice import analyse
    res = analyse(m15_df, cfg)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ict_engine.detectors import basic as B
from ict_engine.detectors.swings import swing_table


def to_daily(m15: pd.DataFrame) -> pd.DataFrame:
    g = m15.groupby(m15.index.normalize())
    return pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(),
                         "close": g.close.last(), "volume": g.volume.sum()})


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    wk = daily.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return wk.dropna(subset=["open"])


@dataclass
class Result:
    m15: pd.DataFrame
    daily: pd.DataFrame
    weekly: pd.DataFrame
    sw15: pd.DataFrame
    swd: pd.DataFrame
    atr15: pd.Series
    disp15: pd.Series
    fvg15: pd.DataFrame
    ob15: pd.DataFrame
    sweeps15: pd.DataFrame
    mss15: pd.DataFrame
    pools15: list
    fvgd: pd.DataFrame
    obd: pd.DataFrame
    range_d: dict | None
    range15: dict | None
    ipda: dict
    qshift: pd.DataFrame
    setups: pd.DataFrame
    bias: dict = field(default_factory=dict)


def _open_pools(m15, sw, tol):
    out = []
    for g in B.equal_levels(sw, tol):
        after = m15.iloc[max(g["bars"]) + 1:]
        hit = np.nonzero((after.high > g["price"]).to_numpy() if g["side"] == "high" else (after.low < g["price"]).to_numpy())[0]
        g["taken_bar"] = max(g["bars"]) + 1 + int(hit[0]) if hit.size else None
        out.append(g)
    return out


def _bias(daily, swd, rng):
    last = daily.close.iloc[-1]
    hi = swd[(swd.side == "high") & (swd.level >= 2)]
    lo = swd[(swd.side == "low") & (swd.level >= 2)]
    trend = "range"
    if len(hi) >= 2 and len(lo) >= 2:
        hh, hl = hi.price.iloc[-1] > hi.price.iloc[-2], lo.price.iloc[-1] > lo.price.iloc[-2]
        trend = "up" if hh and hl else "down" if not hh and not hl else "range"
    zone = "premium" if rng and last > rng["eq"] else "discount"
    above = swd[(swd.side == "high") & swd.unbroken & (swd.price > last)]
    below = swd[(swd.side == "low") & swd.unbroken & (swd.price < last)]
    draw_up = above.nsmallest(1, "price").price.iloc[0] if len(above) else None
    draw_dn = below.nlargest(1, "price").price.iloc[0] if len(below) else None
    draw = draw_dn if trend == "down" else draw_up if trend == "up" else (draw_up if zone == "discount" else draw_dn)
    sentence = (f"Daily structure is {trend} (intermediate highs/lows {'rising' if trend == 'up' else 'falling' if trend == 'down' else 'mixed'}); "
                f"price {last:,.0f} is in the {zone} half of the {rng['low']:,.0f}–{rng['high']:,.0f} range"
                + (f", drawing towards open liquidity at {draw:,.0f}." if draw else "."))
    return {"trend": trend, "zone": zone, "draw": draw, "draw_up": draw_up, "draw_dn": draw_dn, "sentence": sentence, "last": last}


def _setups(m15, sw, sweeps, mss, fvg, atr, cfg, rng_fn):
    """Sweep -> MSS -> FVG setups with a limit entry at CE, simulated forward."""
    e = cfg["entry"]
    mg = cfg["management"]
    h, l, c = m15.high.to_numpy(), m15.low.to_numpy(), m15.close.to_numpy()
    rows = []
    for m in mss.itertuples():
        bull = m.side == "bull"
        want = "sell-side" if bull else "buy-side"
        sw_prior = sweeps[(sweeps.side == want) & (sweeps.bar < m.bar) & (sweeps.bar >= m.bar - 15)] if len(sweeps) else sweeps
        f = fvg[(fvg.side == m.side) & (fvg.bar >= m.bar - 2) & (fvg.bar <= m.bar + 1)]
        if sw_prior.empty or f.empty:
            continue
        s, g = sw_prior.iloc[-1], f.iloc[-1]
        a = float(atr.iloc[m.bar])
        entry = g.ce
        # stop beyond the further of the sweep extreme and the FVG, plus a buffer, at least min_stop_atr away
        if bull:
            stop = min(l[s.bar], g.bottom) - e["stop_buffer_atr"] * a
            stop = min(stop, entry - e.get("min_stop_atr", 0.5) * a)
        else:
            stop = max(h[s.bar], g.top) + e["stop_buffer_atr"] * a
            stop = max(stop, entry + e.get("min_stop_atr", 0.5) * a)
        risk = abs(entry - stop)
        start = int(g.bar) + 2
        fill = None
        for j in range(start, min(start + e["limit_expiry_bars"], len(m15))):
            if (bull and l[j] <= entry) or (not bull and h[j] >= entry):
                fill = j
                break
        known = sw[(sw.bar + 1 < (fill or start)) & (sw.side == ("high" if bull else "low"))]
        cand = []
        for r in known.itertuples():
            brk = r.broken_date
            if pd.notna(brk) and m15.index.get_loc(brk) < (fill or start):
                continue
            if (bull and r.price > entry) or (not bull and r.price < entry):
                cand.append(r.price)
        cand = sorted(cand, reverse=not bull)
        target = next((p for p in cand if abs(p - entry) / risk >= e["min_rr"]), None)
        rr = abs(target - entry) / risk if target else None
        rng = rng_fn(m.bar)
        in_disc = rng is not None and ((entry < rng["eq"]) if bull else (entry > rng["eq"]))
        res, exit_bar, exit_px, be_moved = "no fill", None, None, False
        if fill is not None and target is not None:
            cur_stop = stop
            res = "open"
            for j in range(fill, min(fill + mg["time_stop_bars"] * 4, len(m15))):
                hit_stop = (l[j] <= cur_stop) if bull else (h[j] >= cur_stop)
                hit_tgt = (h[j] >= target) if bull else (l[j] <= target)
                if hit_stop:
                    res, exit_bar, exit_px = ("breakeven" if be_moved else "stop"), j, cur_stop
                    break
                if hit_tgt:
                    res, exit_bar, exit_px = "target", j, target
                    break
                one_r = entry + risk if bull else entry - risk
                if not be_moved and ((bull and h[j] >= one_r) or (not bull and l[j] <= one_r)):
                    cur_stop, be_moved = entry, True
            if res == "open" and exit_bar is None:
                exit_bar = min(fill + mg["time_stop_bars"] * 4, len(m15)) - 1
                exit_px = c[exit_bar]
                res = "time stop" if exit_bar < len(m15) - 1 else "open"
        elif target is None and fill is not None:
            res = "skipped: R:R < 1.5"
        r_mult = None
        if exit_px is not None:
            r_mult = ((exit_px - entry) if bull else (entry - exit_px)) / risk
        checks = {"sweep": True, "MSS by close": True, "FVG entry": True, "discount/premium": in_disc,
                  "R:R ≥ 1.5": rr is not None, "filled": fill is not None}
        grade = "A" if all(checks.values()) else ("B" if sum(checks.values()) >= 5 else "C")
        rows.append({"side": "long" if bull else "short", "sweep_bar": int(s.bar), "sweep_level": s.level, "sweep_type": s.swing_type,
                     "mss_bar": int(m.bar), "mss_level": m.level, "fvg_bar": int(g.bar), "fvg_top": g.top, "fvg_bottom": g.bottom,
                     "entry": entry, "stop": stop, "target": target, "rr": rr, "fill_bar": fill, "exit_bar": exit_bar,
                     "exit": exit_px, "result": res, "R": r_mult, "be_moved": be_moved, "grade": grade,
                     "missing": ", ".join(k for k, v in checks.items() if not v),
                     "mss_time": m15.index[m.bar], "entry_time": m15.index[fill] if fill is not None else pd.NaT})
    return pd.DataFrame(rows)


def analyse(m15: pd.DataFrame, cfg: dict) -> Result:
    daily = to_daily(m15)
    weekly = to_weekly(daily)
    sw15 = swing_table(m15, cfg)
    swd = swing_table(daily, cfg)
    atr15 = B.atr(m15)
    pd_cfg = cfg["pd_arrays"]
    fvg15 = B.fvgs(m15, 0.3)
    ob15 = B.order_blocks(m15, pd_cfg["displacement_atr_mult"], pd_cfg["ob_lookback_bars"])
    sweeps15 = B.sweeps(m15, sw15)
    mss15 = B.mss_events(m15, sw15, cfg["confirmation"]["mss_displacement_atr_mult"])
    pools = _open_pools(m15, sw15, 0.25 * float(atr15.median()))
    fvgd = B.fvgs(daily, 0.2)
    obd = B.order_blocks(daily, pd_cfg["displacement_atr_mult"], pd_cfg["ob_lookback_bars"])
    rng_d = B.dealing_range(swd[swd.level >= 2])
    rng15 = B.dealing_range(sw15[sw15.level >= 2])
    sw15_hi = sw15[sw15.level >= 2]

    def rng_at(bar):
        known = sw15_hi.copy()
        return B.dealing_range(known, upto_bar=bar - 2)

    setups = _setups(m15, sw15, sweeps15, mss15, fvg15, atr15, cfg, rng_at)
    res = Result(m15, daily, weekly, sw15, swd, atr15, B.displacement(m15, pd_cfg["displacement_atr_mult"]),
                 fvg15, ob15, sweeps15, mss15, pools, fvgd, obd, rng_d, rng15,
                 B.ipda_ranges(daily, tuple(cfg["ipda"]["lookbacks"])), B.quarterly_shifts(daily, 40), setups)
    res.bias = _bias(daily, swd, rng_d)
    return res
