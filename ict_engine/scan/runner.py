"""Run the full funnel: market → universe → daily ICT → 45m OTE → rank → report."""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from ict_engine.config import ROOT
from ict_engine.data.providers import nse
from ict_engine.data.resample import to_45m
from ict_engine.data.store import Store
from ict_engine.scan import report
from ict_engine.scan.ote import stage3_symbol
from ict_engine.scan.rank import rank
from ict_engine.scan.stages import (panel_to_frames, stage0_market, stage1_universe, stage2_rs,
                                    stage2_symbol)


def _p(rel):
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def _pool_map(fn, args, workers):
    if workers <= 1 or len(args) < 8:
        return [fn(*a) for a in args]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, *zip(*args), chunksize=8))


def load_inputs(cfg: dict, store: Store):
    sc = cfg["scan"]
    panel = store.read_daily_panel()
    indices = {k: store.read_series("index", k) for k in ("nifty50", "nifty500", "vix")}
    uni_path = _p(sc["universe_file"])
    universe = nse.load_equity_list(uni_path, tuple(sc["series"])) if uni_path.exists() else None
    ex_path = _p(sc["exclude_file"])
    exclude = set()
    if ex_path.exists():
        exclude = {ln.strip() for ln in ex_path.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    ev_path = _p(cfg["filters"]["event_calendar"])
    events = pd.read_csv(ev_path) if ev_path.exists() else None
    return panel, indices, universe, exclude, events


def add_timemachine(final: pd.DataFrame, cfg: dict, store: Store, end, replays: int = 2000) -> pd.DataFrame:
    """Time Machine odds for each finalist (60m pool when cached, else 45m)."""
    from ict_engine.backtest.walkforward import cost_pct
    from ict_engine.sim import timemachine as TM

    wf = cfg["walkforward"]
    rows = []
    for r in final.itertuples():
        b = store.read_series("h1", r.symbol)
        per = 7
        if b is None:
            m15 = store.read_series("m15", r.symbol)
            b, per = (to_45m(m15[m15.index <= end], cfg), 8) if m15 is not None else (None, 8)
        else:
            b = b[b.index <= end]
        try:
            o = TM.run(b, TM.Plan(r.symbol, r.entry, r.stop, r.t1, r.t2, float(b.close.iloc[-1])),
                       TM.TMConfig(replays=replays, valid_sessions=wf["order_valid_sessions"], hold_days=wf["hold_days"],
                                   partial=wf["partial_at_t1"], cost_pct=cost_pct(cfg), atr_bars=10 * per, fan_paths=10))
            rows.append({"symbol": r.symbol, "tm_fill_pct": o["fill_rate_pct"], "tm_avg_R_filled": o["avg_R_filled"],
                         "tm_win_pct": o["win_rate_filled_pct"], "tm_verdict": o["verdict"]})
        except Exception as e:
            rows.append({"symbol": r.symbol, "tm_verdict": f"Time Machine skipped: {e}"})
    return final.merge(pd.DataFrame(rows), on="symbol", how="left")


def run_scan(cfg: dict, as_of=None, fetch_intraday: bool = True, force: bool = False, workers: int = 4,
             out_dir: str | Path | None = None, log=print, timemachine: bool = False, watch: bool = False) -> dict:
    sc = cfg["scan"]
    store = Store(sc["store_dir"])
    panel, indices, universe, exclude, events = load_inputs(cfg, store)
    if panel.empty:
        raise SystemExit("No daily data. Run: python -m scripts.fetch_data --daily --indices")
    if universe is not None:
        panel = panel[panel.symbol.isin(set(universe.SYMBOL))]
    as_of = pd.Timestamp(as_of) if as_of else panel.date.max()
    panel = panel[panel.date <= as_of]
    indices = {k: (v[v.index <= as_of] if v is not None else None) for k, v in indices.items()}
    n_universe = panel.symbol.nunique()
    out = _p(out_dir or f"reports/scans/{as_of:%Y-%m-%d}")
    (out / "charts").mkdir(parents=True, exist_ok=True)
    funnel_rows = []

    # stage 0
    market = stage0_market(indices, panel, cfg)
    log(f"Stage 0 · {market['sentence']}")
    market_ok = market["allowed_side"] != "none"
    if not market_ok and not force:
        log("Stage 0 blocks new longs: continuing as a WATCH LIST (no grade A). Use --strict to stop here.")
    if not market_ok and force == "strict":
        report.write_html(out, as_of, market, [("NSE universe", n_universe), ("stage 0: market allows longs", 0)],
                          pd.DataFrame(), pd.DataFrame())
        (out / "market.json").write_text(json.dumps(market, indent=2, default=str))
        return {"out": out, "market": market, "steps": [], "final": pd.DataFrame()}

    # stage 1
    s1 = stage1_universe(panel, cfg, exclude, events, as_of)
    funnel_rows.append(s1.assign(stage=1)[["stage", "reason"]])
    s1_pass = s1[s1["pass"]].index.tolist()
    log(f"Stage 1 · {n_universe} → {len(s1_pass)} (liquidity, price, volatility, history, exclusions)")

    # stage 2
    frames = panel_to_frames(panel[panel.symbol.isin(s1_pass)])
    s2 = pd.DataFrame(_pool_map(stage2_symbol, [(s, frames[s], cfg) for s in s1_pass], workers))
    bench = indices.get("nifty500") if indices.get("nifty500") is not None else indices.get("nifty50")
    lb = sc["stage2"]["rs_lookback"]
    bench_ret = float(bench.close.pct_change(lb).iloc[-1] * 100) if bench is not None and len(bench) > lb else np.nan
    s2 = stage2_rs(s2, bench_ret, cfg) if len(s2) else s2
    if len(s2):
        funnel_rows.append(s2.set_index("symbol").assign(stage=2)[["stage", "reason"]])
    s2_pass = s2[s2["pass"]].symbol.tolist() if len(s2) else []
    log(f"Stage 2 · {len(s1_pass)} → {len(s2_pass)} (daily bias, discount, near a PD array, room, RS)")

    # stage 3: 15m → 45m for survivors only
    if fetch_intraday and s2_pass:
        from ict_engine.data.providers import yahoo
        log(f"Downloading 15m bars for {len(s2_pass)} symbols (Yahoo, last 60 days)…")
        for sym, df in yahoo.intraday_15m(s2_pass).items():
            store.merge_series("m15", sym, df)
    end = as_of + pd.Timedelta(hours=23, minutes=59)
    m45s, args = {}, []
    ctx = s2.set_index("symbol") if len(s2) else pd.DataFrame()
    for sym in s2_pass:
        m15 = store.read_series("m15", sym)
        if m15 is None:
            continue
        m45 = to_45m(m15[m15.index <= end], cfg)
        m45s[sym] = m45
        args.append((sym, m45, cfg, list(ctx.loc[sym, "daily_bsl_levels"]), watch))
    s3 = pd.DataFrame(_pool_map(stage3_symbol, args, workers)) if args else pd.DataFrame(columns=["symbol", "pass", "state", "reason"])
    missing = [s for s in s2_pass if s not in m45s]
    if missing:
        s3 = pd.concat([s3, pd.DataFrame({"symbol": missing, "pass": False, "state": "no data",
                                          "reason": "no 15m data in the store"})], ignore_index=True)
    if len(s3):
        funnel_rows.append(s3.set_index("symbol").assign(stage=3)[["stage", "reason"]])
    if len(s3):
        s3["pass"] = s3["pass"].astype(bool)
    s3_pass = s3[s3["pass"]] if len(s3) else s3
    log(f"Stage 3 · {len(s2_pass)} → {len(s3_pass)} (45m sweep → MSS → OTE, R:R to T2)")

    # stage 4
    final = pd.DataFrame()
    if len(s3_pass):
        merged = s3_pass.merge(s2.drop(columns=["pass", "reason"]), on="symbol", how="left", suffixes=("", "_d"))
        final = rank(merged, cfg, market_ok).head(sc["stage4"]["top_n"])
        if timemachine and len(final):
            log(f"Time Machine: replaying {len(final)} plan(s)…")
            final = add_timemachine(final, cfg, store, end)
        for r in final.to_dict("records"):
            report.chart(r["symbol"], m45s[r["symbol"]], r, cfg, out / "charts" / f"{r['symbol']}_45m.png")
    log(f"Stage 4 · top {len(final)} ranked; charts in {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")

    # outputs
    funnel = pd.concat(funnel_rows) if funnel_rows else pd.DataFrame()
    funnel.to_csv(out / "funnel.csv")
    cols = ["symbol", "grade", "score", "state", "entry", "stop", "t1", "t2", "rr_t1", "rr_t2", "ote_79", "ote_62",
            "last_close", "dist_to_entry_atr", "qty_1pct", "has_confluence", "sweep_time", "mss_time", "bias",
            "discount", "zone", "rs_pct", "tm_fill_pct", "tm_win_pct", "tm_avg_R_filled", "tm_verdict"]
    if len(final):
        final[[c for c in cols if c in final.columns]].to_csv(out / "scan.csv", index=False)
        (out / "tradingview_watchlist.txt").write_text("\n".join(f"NSE:{s}" for s in final.symbol))
    steps = [("NSE universe", n_universe), ("stage 1: liquid & tradeable", len(s1_pass)),
             ("stage 2: daily ICT context", len(s2_pass)), ("stage 3: 45m OTE setup", len(s3_pass)),
             ("ranked", len(final))]
    report.write_html(out, as_of, market, steps, final, s3, watch_only=not market_ok)
    (out / "market.json").write_text(json.dumps(market, indent=2, default=str))
    return {"out": out, "market": market, "steps": steps, "final": final, "stage1": s1, "stage2": s2, "stage3": s3,
            "m45": m45s, "store": store, "end": end, "as_of": as_of, "market_ok": market_ok}
