"""Walk-forward validation of the ICT scanner (no lookahead).

Three steps:
    python -m scripts.walkforward prepare --start 2025-11-13 --end 2026-11-12
        stages 0-2 for every trading day (offline, from data/store) → reports/walkforward/plan.parquet
        and reports/walkforward/symbols_needed.txt
    python -m scripts.walkforward fetch
        intraday bars for the symbols in symbols_needed.txt (needs internet: run in your terminal)
          60m from Yahoo (730 days)  → data/store/h1    used by --tf 60m (12-month test)
          15m from Yahoo (60 days)   → data/store/m15   used by --tf 45m (last ~60 days only)
    python -m scripts.walkforward run --tf 60m
        stage 3 on each scan day, simulate every order, write the report
        → reports/walkforward/<tf>_<start>_<end>/index.html, trades.csv, summary.json
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from ict_engine.backtest import walkforward as W
from ict_engine.config import ROOT, load_config
from ict_engine.data.resample import to_45m
from ict_engine.data.store import Store
from ict_engine.scan.runner import load_inputs
from ict_engine.scan.stages import panel_to_frames

OUT = ROOT / "reports" / "walkforward"


def _s2_job(args):
    sym, d, dates, cfg = args
    try:
        return W.stage2_series(sym, d, dates, cfg)
    except Exception:
        return pd.DataFrame()


def prepare(cfg, start, end, workers):
    store = Store(cfg["scan"]["store_dir"])
    panel, indices, universe, exclude, _ = load_inputs(cfg, store)
    if universe is not None:
        panel = panel[panel.symbol.isin(set(universe.SYMBOL))]
    dates = sorted(d for d in panel.date.unique() if pd.Timestamp(start) <= d <= pd.Timestamp(end))
    if not dates:
        raise SystemExit("No trading days in that range in the daily panel.")
    print(f"{len(dates)} trading days, {panel.symbol.nunique()} symbols, daily data from {panel.date.min():%d %b %Y}")
    s0 = W.stage0_series(indices, panel, dates, cfg)
    print(f"Stage 0: market allowed longs on {int(s0.market_ok.sum())}/{len(s0)} days")
    s1 = W.stage1_series(panel, cfg, frozenset(exclude))
    s1 = s1[s1.date.isin(dates) & s1.s1]
    print(f"Stage 1: {len(s1):,} (day, symbol) pairs; {s1.symbol.nunique()} symbols ever pass")
    frames = panel_to_frames(panel[panel.symbol.isin(s1.symbol.unique())])
    jobs = [(sym, frames[sym], sorted(g.date), cfg) for sym, g in s1.groupby("symbol")]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        parts = []
        for k, df in enumerate(ex.map(_s2_job, jobs, chunksize=8), 1):
            parts.append(df)
            if k % 100 == 0 or k == len(jobs):
                print(f"  stage 2 context: {k}/{len(jobs)} symbols")
    ctx = pd.concat([p for p in parts if len(p)], ignore_index=True)
    ctx = ctx.join(s0, on="date")
    bench = indices.get("nifty500") if indices.get("nifty500") is not None else indices.get("nifty50")
    bench_ret = bench.close.pct_change(cfg["scan"]["stage2"]["rs_lookback"]) * 100
    for name, rules in W.ABLATIONS.items():
        m = W.apply_stage2(ctx, bench_ret, cfg, rules)
        if rules.get("market", True):
            m &= ctx.market_ok
        ctx[f"ok_{name}"] = m
    ok_cols = [c for c in ctx.columns if c.startswith("ok_")]
    ctx["ok_any"] = ctx[ok_cols].any(axis=1)
    OUT.mkdir(parents=True, exist_ok=True)
    ctx.to_parquet(OUT / "plan.parquet", index=False) if W_has_parquet() else ctx.to_pickle(OUT / "plan.pkl")
    s0.to_csv(OUT / "market_by_day.csv")
    need = sorted(ctx[ctx.ok_any].symbol.unique())
    (OUT / "symbols_needed.txt").write_text("\n".join(need))
    per = {n: int(ctx[f"ok_{n}"].sum()) for n in W.ABLATIONS}
    print("Stage 2 survivors (day, symbol pairs) per rule set: " + ", ".join(f"{k} {v}" for k, v in per.items()))
    print(f"{len(need)} symbols need intraday data → run: python -m scripts.walkforward fetch")


def W_has_parquet():
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def load_plan():
    p = OUT / "plan.parquet"
    return pd.read_parquet(p) if p.exists() else pd.read_pickle(OUT / "plan.pkl")


def fetch(cfg):
    from ict_engine.data.providers import yahoo
    store = Store(cfg["scan"]["store_dir"])
    syms = [s for s in (OUT / "symbols_needed.txt").read_text().split() if s]
    print(f"Downloading intraday bars for {len(syms)} symbols…")
    for sym, df in yahoo.intraday(syms, "60m", "730d", log=print).items():
        store.merge_series("h1", sym, df)
    for sym, df in yahoo.intraday(syms, "15m", "60d", log=print).items():
        store.merge_series("m15", sym, df)
    print("Done. Now: python -m scripts.walkforward run --tf 60m   (and --tf 45m for the last ~60 days)")


def run(cfg, tf, workers):
    wf = cfg["walkforward"]
    store = Store(cfg["scan"]["store_dir"])
    ctx = load_plan()
    plan = ctx[ctx.ok_any]
    intraday, cover = {}, []
    for sym in plan.symbol.unique():
        if tf == "60m":
            b = store.read_series("h1", sym)
        else:
            m15 = store.read_series("m15", sym)
            b = to_45m(m15, cfg) if m15 is not None else None
        if b is not None and len(b):
            intraday[sym] = b
            cover.append((b.index[0], b.index[-1]))
    if not intraday:
        raise SystemExit("No intraday data. Run: python -m scripts.walkforward fetch")
    bars_per_day = int(pd.Series([len(g) for _, g in next(iter(intraday.values())).groupby(lambda t: t.normalize())]).median())
    first = min(c[0] for c in cover)
    plan = plan[plan.date >= first.normalize()]
    sim = W.SimCfg(wf["order_valid_sessions"], wf["hold_days"], wf["partial_at_t1"], W.cost_pct(cfg))
    print(f"{tf}: {len(intraday)} symbols with data from {first:%d %b %Y}; {bars_per_day} bars/day; "
          f"{plan.date.nunique()} scan days; round-trip cost {sim.cost_pct_round_trip:.3f}% of price")
    occ = W.run_trades(intraday, plan, cfg, sim, bars_per_day, wf["window_bars"], workers)
    if occ.empty:
        print("No actionable setups in the test window.")
    start, end = plan.date.min(), plan.date.max()
    out = OUT / f"{tf}_{start:%Y%m%d}_{end:%Y%m%d}"
    out.mkdir(parents=True, exist_ok=True)
    occ.to_csv(out / "all_setups.csv", index=False)
    results = {}
    for name in W.ABLATIONS:
        allowed = set(zip(ctx.loc[ctx[f"ok_{name}"], "symbol"], ctx.loc[ctx[f"ok_{name}"], "date"]))
        sel = W.select_orders(occ, allowed) if len(occ) else occ
        if name == "require_confluence" and len(sel):
            sel = sel[sel.has_confluence]
        results[name] = sel
    base = results["base"]
    base.to_csv(out / "trades.csv", index=False)
    summary = {"timeframe": tf, "test_start": str(start.date()), "test_end": str(end.date()),
               "symbols_with_data": len(intraday), "scan_days": int(plan.date.nunique()),
               "cost_pct_round_trip": round(sim.cost_pct_round_trip, 4),
               "rule_sets": {k: W.metrics(v) for k, v in results.items()}}
    if len(base):
        b = base.copy()
        b["grade"] = np.where(b.has_confluence & (b.bias == "up"), "A-like", "B-like")
        summary["base_by_grade"] = {g: W.metrics(x) for g, x in b.groupby("grade")}
        nm = results["no_market_filter"]
        if len(nm):
            summary["market_ok_vs_blocked"] = {("market allowed" if k else "market blocked"): W.metrics(x)
                                               for k, x in nm.groupby(nm.market_ok.fillna(False))}
        b["month"] = pd.to_datetime(b.scan_date).dt.to_period("M").astype(str)
        summary["base_by_month"] = {m: W.metrics(x) for m, x in b.groupby("month")}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    from ict_engine.backtest import wf_report
    wf_report.write(out, summary, results)
    print(json.dumps(summary["rule_sets"], indent=1, default=str))
    print(f"\nOpen: {out / 'index.html'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "fetch", "run"])
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--tf", choices=["60m", "45m"], default="60m")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    cfg = load_config()
    if a.step == "prepare":
        end = pd.Timestamp(a.end) if a.end else pd.Timestamp.today().normalize()
        start = pd.Timestamp(a.start) if a.start else end - pd.Timedelta(days=365)
        prepare(cfg, start, end, a.workers)
    elif a.step == "fetch":
        fetch(cfg)
    else:
        run(cfg, a.tf, a.workers)


if __name__ == "__main__":
    main()
