"""Swing Time Machine: replay a planned swing trade 10,000 times before risking a rupee.

Adapted from the day-trade Time Machine (Monte Carlo over the stock's own bars) for multi-day
swing trades with an unfilled limit entry, overnight gaps, partial exits and Indian costs.

How a replay is built
---------------------
1. Pool: every FULL past session of the stock's intraday bars (60m: ~2 years from Yahoo; or 45m
   built from 15m), each bar stored as ratios (open, high, low, close) / previous bar's close.
   The first bar of a session is relative to the previous session's last close, so the pool
   carries the stock's real overnight gaps. Sessions with missing bars are left out.
2. Optional adjustments (both on by default):
   * volatility scaling: every ratio's distance from 1 is multiplied by k = (today's ATR% of the
     intraday bars) / (the pool's average bar range %), so a quiet stock is not replayed with an
     old, wild regime;
   * drift removal: each session's ratios are divided by the pool's average daily close-to-close
     growth, spread over its bars, so a stock that rallied hard in the past does not make every
     long look good.
3. A replay chains ``days`` randomly drawn whole sessions (with replacement) starting from the
   last close, giving intraday bars across several days with real gaps and real day shapes.
4. Each replay runs through ict_engine.sim.trade.manage, the same rules as the walk-forward:
   limit at the planned entry valid for ``valid_sessions`` sessions; stop before targets in a bar;
   exit at the open on a gap through the stop; ``partial`` off at T1 then stop to breakeven; the
   rest to T2; time stop after ``hold_days`` sessions. Round-trip delivery costs are subtracted.

The verdict compares, among filled replays that reached T1 or the stop first, the share that
reached T1 first with the share needed to break even at T1's R: 1 / (1 + R_T1). It is a check of
the plan against this stock's own past behaviour, not a forecast: news, results, circuit limits
and regime changes can do what the pool never did. Same inputs and seed give the same numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ict_engine.sim.trade import manage

COIN, STRONG = 0.05, 0.15


@dataclass
class Plan:
    symbol: str
    entry: float
    stop: float
    t1: float
    t2: float = np.nan
    last_close: float = np.nan
    side: str = "long"


@dataclass
class TMConfig:
    replays: int = 10000
    seed: int = 19
    days: int = 15                 # sessions simulated after the scan
    valid_sessions: int = 2
    hold_days: int = 15
    partial: float = 0.5
    scale_vol: bool = True
    remove_drift: bool = True
    atr_bars: int = 70             # bars used for "today's" volatility (~10 sessions of 60m)
    cost_pct: float = 0.0          # round-trip, % of price
    fan_paths: int = 2000
    extra: dict = field(default_factory=dict)


def build_pool(bars: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """(sessions, bars_per_session, 4) array of ratios, plus info about what was kept."""
    day = bars.index.normalize()
    counts = pd.Series(1, index=day).groupby(level=0).sum()
    per = int(counts.mode().iloc[0])
    full_days = counts[counts == per].index
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    prev_c = np.r_[np.nan, c[:-1]]
    ratios = np.stack([o / prev_c, h / prev_c, l / prev_c, c / prev_c], axis=1)
    keep = []
    dlist = list(counts.index)
    for k, d in enumerate(dlist):
        if d not in full_days or k == 0:
            continue
        idx = np.nonzero(day == d)[0]
        # the previous bar must be the previous session's last bar (no hole between the two)
        if counts.loc[dlist[k - 1]] != per or not np.all(np.isfinite(ratios[idx])):
            continue
        keep.append(ratios[idx])
    pool = np.array(keep)
    info = {"bars_per_session": per, "sessions": len(pool),
            "left_out": int(len(counts) - len(pool)),
            "from": str(full_days.min().date()) if len(full_days) else None,
            "to": str(full_days.max().date()) if len(full_days) else None}
    return pool, info


def adjust_pool(pool: np.ndarray, bars: pd.DataFrame, cfg: TMConfig) -> tuple[np.ndarray, dict]:
    p = pool.copy()
    info = {"vol_scale": 1.0, "drift_removed_pct_per_day": 0.0}
    if cfg.remove_drift and len(p):
        daily = np.prod(p[:, :, 3], axis=1)                  # close-to-close growth of each session
        g = float(np.exp(np.mean(np.log(daily))))
        per_bar = g ** (1.0 / p.shape[1])
        p = p / per_bar                                      # same factor on o/h/l/c of every bar
        info["drift_removed_pct_per_day"] = round((g - 1) * 100, 4)
    if cfg.scale_vol and len(p):
        rng = (bars.high - bars.low) / bars.close.shift(1)
        now = float(rng.iloc[-cfg.atr_bars:].mean())
        pool_rng = float(np.mean(p[:, :, 1] - p[:, :, 2]))
        k = now / pool_rng if pool_rng > 0 else 1.0
        k = float(np.clip(k, 0.33, 3.0))
        p = 1 + (p - 1) * k
        info["vol_scale"] = round(k, 3)
    return p, info


def replay(pool: np.ndarray, start_price: float, days: int, rng: np.random.Generator):
    """One synthetic future: arrays o, h, l, c, day for ``days`` drawn sessions."""
    idx = rng.integers(0, len(pool), size=days)
    r = pool[idx].reshape(-1, 4)                             # (days * per, 4)
    c = start_price * np.cumprod(r[:, 3])
    prev = np.r_[start_price, c[:-1]]
    o, h, l = prev * r[:, 0], prev * r[:, 1], prev * r[:, 2]
    day = np.repeat(np.arange(days), pool.shape[1])
    return o, h, l, c, day


def run(bars: pd.DataFrame, plan: Plan, cfg: TMConfig) -> dict:
    if plan.side != "long":
        raise ValueError("long setups only (delivery)")
    if not plan.stop < plan.entry < plan.t1:
        raise ValueError(f"need stop < entry < T1 (got {plan.stop}, {plan.entry}, {plan.t1})")
    pool0, pinfo = build_pool(bars)
    if pinfo["sessions"] < 20:
        raise ValueError(f"only {pinfo['sessions']} full sessions in the data; need at least 20")
    pool, ainfo = adjust_pool(pool0, bars, cfg)
    per = pool.shape[1]
    start = float(plan.last_close if plan.last_close == plan.last_close else bars.close.iloc[-1])
    rng = np.random.default_rng(cfg.seed)
    results, Rs, exit_day, fills, first_side = [], [], [], 0, []
    end_prices = np.empty(cfg.replays)
    for n in range(cfg.replays):
        o, h, l, c, day = replay(pool, start, cfg.days, rng)
        res, fi, xi, fill, R = manage(o, h, l, c, day, 0, plan.entry, plan.stop, plan.t1, plan.t2,
                                      cfg.valid_sessions, cfg.hold_days * per, cfg.partial)
        end_prices[n] = c[-1]
        results.append(res)
        if fi >= 0:
            fills += 1
            cost_r = cfg.cost_pct / 100 * fill / (fill - plan.stop) if fill > plan.stop else 0.0
            Rs.append(R - cost_r)
            exit_day.append(int(day[xi]) + 1)
            first_side.append("T1" if res.startswith("T1") else "stop" if res.startswith(("stop", "gap")) else "none")
        else:
            Rs.append(0.0)                                   # no fill: no trade, no cost
    res_s = pd.Series(results)
    share = res_s.value_counts(normalize=True)
    filled_R = np.array([r for r, x in zip(Rs, results) if x not in ("no fill", "no data after scan")])
    risk0 = plan.entry - plan.stop
    r_t1 = (plan.t1 - plan.entry) / risk0
    fs = pd.Series(first_side).value_counts() if first_side else pd.Series(dtype=int)
    t1n, stn = int(fs.get("T1", 0)), int(fs.get("stop", 0))
    out = {
        "plan": plan.__dict__, "config": {k: v for k, v in cfg.__dict__.items() if k != "extra"},
        "pool": {**pinfo, **ainfo}, "start_price": round(start, 2),
        "outcomes_pct": {k: round(float(v) * 100, 1) for k, v in share.items()},
        "fill_rate_pct": round(fills / cfg.replays * 100, 1),
        "avg_R_all": round(float(np.mean(Rs)), 3),
        "avg_R_filled": round(float(filled_R.mean()), 3) if len(filled_R) else None,
        "win_rate_filled_pct": round(float((filled_R > 0).mean() * 100), 1) if len(filled_R) else None,
        "median_exit_session": int(np.median(exit_day)) if exit_day else None,
        "end_price": {"median": round(float(np.median(end_prices)), 2),
                      "p5": round(float(np.percentile(end_prices, 5)), 2),
                      "p95": round(float(np.percentile(end_prices, 95)), 2)},
        "r_at_t1": round(r_t1, 2), "t1_first": t1n, "stop_first": stn,
    }
    out["verdict"], out["notes"] = verdict(out)
    out["fan"] = fan(pool, start, cfg)
    return out


def verdict(o: dict) -> tuple[str, list]:
    t1n, stn, r = o["t1_first"], o["stop_first"], o["r_at_t1"]
    notes = []
    if t1n + stn == 0:
        return "No filled replay reached T1 or the stop: the time stop decides every one.", notes
    share, even = t1n / (t1n + stn), 1 / (1 + r)
    d = share - even
    head = ("Close to break-even" if abs(d) < COIN else
            ("Leans toward the target" if d > 0 else "Leans toward the stop") if abs(d) < STRONG else
            ("Strongly toward the target" if d > 0 else "Strongly toward the stop"))
    text = (f"{head}: at {r:g}R to T1 the target has to come first in {even * 100:.0f} % of the filled replays "
            f"that hit one side; it did in {share * 100:.0f} %.")
    nf = 100 - o["fill_rate_pct"]
    if nf > 40:
        notes.append(f"{nf:.0f} % of replays never filled the limit within the order's life: no trade, no loss.")
    a = o.get("avg_R_filled")
    if a is not None and abs(d) >= COIN and (a > 0) != (d > 0):
        notes.append(f"Average R of filled replays is {a:+.2f} all the same (partials, breakeven exits and costs).")
    return text, notes


def fan(pool: np.ndarray, start: float, cfg: TMConfig) -> dict:
    """Percentile bands of the end-of-session close for the fan chart (separate draws, same seed)."""
    rng = np.random.default_rng(cfg.seed)
    per = pool.shape[1]
    closes = np.empty((cfg.fan_paths, cfg.days + 1))
    for n in range(cfg.fan_paths):
        _, _, _, c, _ = replay(pool, start, cfg.days, rng)
        closes[n] = np.r_[start, c[per - 1::per]]
    q = np.percentile(closes, [5, 25, 50, 75, 95], axis=0)
    return {"sessions": list(range(cfg.days + 1)), "bands": q.round(2).tolist()}


# ----------------------------------------------------------------------------- reporting

def text_report(o: dict, history: dict | None = None) -> str:
    p, pl, cf = o["plan"], o["pool"], o["config"]
    risk = p["entry"] - p["stop"]
    names = ["no fill", "stop", "stop (gap)", "gap below stop at fill", "T1 then breakeven", "T1 then BE (gap)",
             "T1", "T1 + T2", "time stop", "open at end of data"]
    lines = [
        f"{p['symbol']} long · limit entry {p['entry']:,.2f} · stop {p['stop']:,.2f} (risk {risk:,.2f}) · "
        f"T1 {p['t1']:,.2f} ({o['r_at_t1']:g}R)" + (f" · T2 {p['t2']:,.2f}" if p['t2'] == p['t2'] else ""),
        f"{cf['replays']:,} replays of the next {cf['days']} sessions from {o['start_price']:,.2f}, seed {cf['seed']}. "
        f"Pool: {pl['sessions']} real sessions ({pl['from']} → {pl['to']}, {pl['bars_per_session']} bars each), "
        f"volatility ×{pl['vol_scale']}, drift removed {pl['drift_removed_pct_per_day']:+.3f}%/day.",
        "",
    ]
    for k in names:
        v = o["outcomes_pct"].get(k)
        if v:
            lines.append(f"  {k:<26}{v:5.1f} %")
    lines += [
        "",
        f"  Fill rate {o['fill_rate_pct']} % · win rate when filled {o['win_rate_filled_pct']} % · "
        f"average R when filled {o['avg_R_filled']:+.2f} · per order (no fill = 0) {o['avg_R_all']:+.2f}  (after costs)",
        f"  Median exit in session {o['median_exit_session']} · close after {cf['days']} sessions: median "
        f"{o['end_price']['median']:,.2f} (90 % between {o['end_price']['p5']:,.2f} and {o['end_price']['p95']:,.2f})",
        "",
    ]
    if history:
        lines.append(history.get("text", ""))
        lines.append("")
    lines.append(o["verdict"])
    lines += o["notes"]
    lines.append("A replay of this stock's own past sessions, not a forecast. Education only, not financial advice.")
    return "\n".join(lines)


def fan_png(o: dict, path, title: str | None = None):
    from ict_engine.viz.mpl import C, plt
    p, f = o["plan"], o["fan"]
    x = f["sessions"]
    b = np.array(f["bands"])
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 5.2), gridspec_kw={"width_ratios": [2.2, 1]})
    ax.fill_between(x, b[0], b[4], color=C["blue"], alpha=0.12, label="90 % of replays")
    ax.fill_between(x, b[1], b[3], color=C["blue"], alpha=0.25, label="middle half")
    ax.plot(x, b[2], color=C["blue"], lw=2, label="median")
    for v, lab, col in ((p["entry"], "entry", C["blue"]), (p["stop"], "stop", C["dn"]), (p["t1"], "T1", C["up"]),
                        (p["t2"], "T2", C["up"])):
        if v == v:
            ax.axhline(v, color=col, ls="--" if lab != "entry" else "-", lw=1)
            ax.text(x[-1] + 0.2, v, f" {lab} {v:,.2f}", color=col, va="center", fontsize=8, fontweight="bold")
    ax.set_xlim(0, x[-1] + 3)
    ax.set_xlabel("sessions after the scan")
    ax.set_title(title or f"{p['symbol']}: where {o['config']['fan_paths']:,} replays went", loc="left", fontweight="bold")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="y", color="#eeebe5")
    oc = o["outcomes_pct"]
    order = [k for k in ("no fill", "stop", "stop (gap)", "T1 then breakeven", "T1 then BE (gap)", "T1", "T1 + T2",
                         "time stop", "open at end of data", "gap below stop at fill") if oc.get(k)]
    cols = [C["grey"] if k == "no fill" else C["dn"] if k.startswith(("stop", "gap")) else
            C["gold"] if "breakeven" in k or "BE" in k or k == "time stop" else C["up"] for k in order]
    ax2.barh(order[::-1], [oc[k] for k in order][::-1], color=cols[::-1])
    for i, k in enumerate(order[::-1]):
        ax2.text(oc[k] + 0.5, i, f"{oc[k]:.1f}%", va="center", fontsize=8)
    ax2.set_title(f"Outcomes · avg R filled {o['avg_R_filled']:+.2f}", loc="left", fontweight="bold")
    ax2.set_xlim(0, max(oc.values()) * 1.25)
    fig.text(0.01, 0.01, o["verdict"], fontsize=8.5, color=C["ink"])
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=120)
    plt.close(fig)
