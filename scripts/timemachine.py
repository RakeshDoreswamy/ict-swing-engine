"""Swing Time Machine: replay a planned swing trade 10,000 times from the stock's own sessions.

    python -m scripts.timemachine --symbol ZFCVINDIA                 # plan from the latest scan
    python -m scripts.timemachine --symbol RELIANCE --entry 1290 --stop 1262 --t1 1340 --t2 1365
    python -m scripts.timemachine --symbol ZFCVINDIA --tf 45m        # 45m pool (last ~60 days only)
    python -m scripts.timemachine --symbol ZFCVINDIA --keep-drift --no-vol-scale
Writes reports/timemachine/<SYMBOL>_<date>.png and .json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ict_engine.backtest.walkforward import cost_pct
from ict_engine.config import ROOT, load_config
from ict_engine.data.resample import to_45m
from ict_engine.data.store import Store
from ict_engine.sim import timemachine as TM


def latest_plan(symbol: str):
    scans = sorted((ROOT / "reports" / "scans").glob("*/scan.csv"))
    for f in reversed(scans):
        df = pd.read_csv(f)
        row = df[df.symbol == symbol]
        if len(row):
            r = row.iloc[0]
            return r, f.parent.name
    return None, None


def load_bars(cfg, symbol: str, tf: str):
    st = Store(cfg["scan"]["store_dir"])
    if tf == "60m":
        b = st.read_series("h1", symbol)
        if b is not None:
            return b, "60m"
    m15 = st.read_series("m15", symbol)
    if m15 is None:
        raise SystemExit(f"No intraday data for {symbol}. Run: python -m scripts.fetch_data --m15 {symbol}")
    return to_45m(m15, cfg), "45m"


def history(symbol: str) -> dict:
    """This stock's past setups and the universe base rate, from the latest walk-forward run."""
    runs = sorted((ROOT / "reports" / "walkforward").glob("*/trades.csv"))
    if not runs:
        return {"text": "History: no walk-forward run yet (python -m scripts.walkforward run)."}
    d = runs[-1].parent
    base = pd.read_csv(d / "trades.csv")
    base = base[base.R.notna()]
    allx = pd.read_csv(d / "all_setups.csv") if (d / "all_setups.csv").exists() else base
    mine = allx[(allx.symbol == symbol)].drop_duplicates("mss_time")
    mine_t = mine[mine.R.notna()] if "R" in mine else mine.iloc[0:0]
    t = (f"History ({d.name}): {symbol} had {len(mine)} past setups, {len(mine_t)} filled"
         + (f" (avg {mine_t.R.mean():+.2f}R; " + ", ".join(f"{k} {v}" for k, v in mine_t.result.value_counts().items()) + ")"
            if len(mine_t) else "") +
         f". All stocks under the base rules: {len(base)} trades, win rate {(base.R > 0).mean() * 100:.0f} %, "
         f"avg {base.R.mean():+.2f}R.")
    return {"text": t, "run": d.name, "symbol_setups": int(len(mine)), "symbol_filled": int(len(mine_t)),
            "base_trades": int(len(base)), "base_avg_R": round(float(base.R.mean()), 3) if len(base) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--entry", type=float)
    ap.add_argument("--stop", type=float)
    ap.add_argument("--t1", type=float)
    ap.add_argument("--t2", type=float)
    ap.add_argument("--tf", choices=["60m", "45m"], default="60m")
    ap.add_argument("--replays", type=int, default=10000)
    ap.add_argument("--days", type=int, default=15)
    ap.add_argument("--seed", type=int, default=19)
    ap.add_argument("--keep-drift", action="store_true")
    ap.add_argument("--no-vol-scale", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    sym = a.symbol.upper()
    src = "flags"
    if a.entry is None:
        r, scan = latest_plan(sym)
        if r is None:
            raise SystemExit(f"{sym} is not in any scan.csv; give --entry --stop --t1 [--t2]")
        a.entry, a.stop, a.t1, a.t2 = float(r.entry), float(r.stop), float(r.t1), float(r.t2)
        src = f"scan {scan}"
    bars, tf = load_bars(cfg, sym, a.tf)
    wf = cfg["walkforward"]
    tmc = TM.TMConfig(replays=a.replays, seed=a.seed, days=a.days, valid_sessions=wf["order_valid_sessions"],
                      hold_days=wf["hold_days"], partial=wf["partial_at_t1"], scale_vol=not a.no_vol_scale,
                      remove_drift=not a.keep_drift, cost_pct=cost_pct(cfg),
                      atr_bars=10 * (7 if tf == "60m" else 8))
    plan = TM.Plan(sym, a.entry, a.stop, a.t1, a.t2 if a.t2 is not None else float("nan"), float(bars.close.iloc[-1]))
    out = TM.run(bars, plan, tmc)
    hist = history(sym)
    print(f"[{tf} pool · plan from {src} · data to {bars.index[-1]:%d %b %Y %H:%M}]")
    print(TM.text_report(out, hist))
    d = ROOT / "reports" / "timemachine"
    d.mkdir(parents=True, exist_ok=True)
    stem = f"{sym}_{bars.index[-1]:%Y%m%d}"
    TM.fan_png(out, d / f"{stem}.png", f"{sym}: where {tmc.fan_paths:,} replays went ({tf} pool)")
    (d / f"{stem}.json").write_text(json.dumps({**out, "history": hist, "timeframe": tf, "plan_source": src},
                                               indent=1, default=str))
    print(f"\nChart: {(d / (stem + '.png')).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
