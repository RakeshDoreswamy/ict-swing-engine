"""Daily routine: screen → filter → ICT strategy → sort → list of possible entries.

    python -m scripts.daily --fetch          # after 15:30: update data, then build today's list
    python -m scripts.daily                  # use cached daily data (15m still downloads for candidates)
    python -m scripts.daily --wide           # relax the daily filters (discount, zone, RS) to see more names
    python -m scripts.daily --no-fetch-intraday --date 2026-11-12   # replay a day from the cache

Every stock that passes the market/universe/daily stages is put into one bucket:
  1 IN ZONE      sweep → MSS done, price inside the 62–79 % OTE band now      → limit at 70.5 %
  2 WAITING      sweep → MSS done, pullback not reached the band yet          → limit or alert at the band
  3 LEG RUNNING  sweep → MSS done, the rally is still making new highs        → wait; the band will move up
  4 SETTING UP   sell-side sweep done, no MSS yet                             → alert above the trigger
  near miss      passed the daily stages, no 45m setup (reason shown)
Buckets 1-2 get a full plan, quantity at 1 % risk, an A-like/B-like label and Time Machine odds.
Outputs: reports/daily/<date>/index.html, watchlist.csv, tradingview_watchlist.txt (import into TradingView,
then add the "ICT Swing Engine" indicator to check each chart).
"""
from __future__ import annotations

import argparse
import copy
import html
import os
import subprocess
import sys

import numpy as np
import pandas as pd

from ict_engine.config import ROOT, load_config
from ict_engine.scan import report
from ict_engine.scan.rank import rank
from ict_engine.scan.runner import add_timemachine, run_scan

BUCKETS = [("in_zone", "IN ZONE", "Limit buy at the 70.5 % line now; stop and targets below."),
           ("waiting", "WAITING", "Structure has shifted; place the limit (valid 2 sessions) or alert at the band top."),
           ("leg_running", "LEG RUNNING", "Rally still making new highs: wait for it to stop, the band will move up."),
           ("setting_up", "SETTING UP", "Sweep done: set an alert for a close above the trigger (that is the MSS).")]


def f(x, d=2):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.{d}f}"


def build(res, cfg, tm: bool) -> pd.DataFrame:
    s2, s3 = res["stage2"], res["stage3"]
    if s3 is None or not len(s3):
        return pd.DataFrame()
    df = s3.merge(s2.drop(columns=["pass", "reason"]), on="symbol", how="left", suffixes=("", "_d"))
    df["bucket"] = df["state"].where(df["state"].isin([b[0] for b in BUCKETS]), "near_miss")
    plan = df[df.bucket.isin(["in_zone", "waiting"])].copy()
    if len(plan):
        plan = rank(plan, cfg, res["market_ok"])
        plan["a_like"] = plan.has_confluence.astype(bool) & (plan.bias == "up")
        plan["rr_ok"] = plan["rr_t2"] >= cfg["scan"]["stage3"]["min_rr_t2"]
        if tm:
            plan = add_timemachine(plan, cfg, res["store"], res["end"])
        df = pd.concat([plan, df[~df.symbol.isin(plan.symbol)]], ignore_index=True)
    order = {b[0]: i for i, b in enumerate(BUCKETS)} | {"near_miss": 9}
    df["_b"] = df.bucket.map(order)
    df["_a"] = ~df.get("a_like", pd.Series(False, index=df.index)).astype("boolean").fillna(False).astype(bool)
    df["_tm"] = -df.get("tm_avg_R_filled", pd.Series(np.nan, index=df.index)).fillna(-9)
    df["_d"] = df.get("dist_to_entry_atr", pd.Series(np.nan, index=df.index)).abs().fillna(
        df.get("dist_to_trigger_atr", pd.Series(np.nan, index=df.index))).fillna(99)
    return df.sort_values(["_b", "_a", "_tm", "_d"]).drop(columns=["_b", "_a", "_tm", "_d"]).reset_index(drop=True)


def plan_cells(r) -> str:
    if r.bucket in ("in_zone", "waiting"):
        tm = getattr(r, "tm_verdict", None)
        tmh = ""
        if isinstance(tm, str):
            avg = getattr(r, "tm_avg_R_filled", np.nan)
            tmh = (f"<br><small>Time Machine: fill {f(getattr(r, 'tm_fill_pct', np.nan), 0)} % · win "
                   f"{f(getattr(r, 'tm_win_pct', np.nan), 0)} % · avg {f(avg)}R when filled. {html.escape(tm)}</small>")
        return (f"<td>{f(r.entry)}</td><td>{f(r.stop)}</td><td>{f(r.t1)} / {f(r.t2)}</td><td>{f(r.rr_t2)}</td>"
                f"<td>{int(r.qty_1pct) if r.qty_1pct == r.qty_1pct else '—'}</td>"
                f"<td>{'A-like' if r.a_like else 'B-like'}{'' if r.rr_ok else ' · R:R low'}{tmh}</td>")
    if r.bucket == "leg_running":
        return (f"<td colspan='3'>leg {f(r.leg_low)} → {f(r.leg_high)} (still rising) · provisional OTE "
                f"{f(r.ote_79)}–{f(r.ote_62)}</td><td></td><td></td><td></td>")
    if r.bucket == "setting_up":
        return (f"<td colspan='3'>sweep low {f(r.sweep_low)} ({pd.Timestamp(r.sweep_time):%d %b %H:%M}) · "
                f"<b>trigger: close above {f(r.trigger)}</b> ({f(r.dist_to_trigger_atr, 1)} ATR away)</td><td></td><td></td><td></td>")
    return f"<td colspan='6' class='muted'>{html.escape(str(r.reason))}</td>"


def write(out, res, wl: pd.DataFrame, wide: bool):
    out.mkdir(parents=True, exist_ok=True)
    (out / "charts").mkdir(exist_ok=True)
    cfg = res["cfg"]
    for r in wl[wl.bucket.isin(["in_zone", "waiting"])].to_dict("records"):
        report.chart(r["symbol"], res["m45"][r["symbol"]], r, cfg, out / "charts" / f"{r['symbol']}_45m.png")
    keep = [c for c in ["symbol", "bucket", "state", "a_like", "grade", "score", "entry", "stop", "t1", "t2", "rr_t2",
                        "ote_79", "ote_62", "last_close", "dist_to_entry_atr", "qty_1pct", "tm_fill_pct", "tm_win_pct",
                        "tm_avg_R_filled", "tm_verdict", "trigger", "sweep_low", "dist_to_trigger_atr", "leg_low",
                        "leg_high", "bias", "discount", "zone", "rs_pct", "reason"] if c in wl.columns]
    wl[keep].to_csv(out / "watchlist.csv", index=False)
    tv = []
    for key, name, _ in BUCKETS:
        syms = wl[wl.bucket == key].symbol.tolist()
        if syms:
            tv.append(f"###{name}")
            tv += [f"NSE:{s}" for s in syms]
    (out / "tradingview_watchlist.txt").write_text(",".join(tv))
    counts = {k: int((wl.bucket == k).sum()) for k, _, _ in BUCKETS}
    sections = ""
    for key, name, how in BUCKETS + [("near_miss", "NEAR MISSES", "Passed the daily stages; no 45m setup.")]:
        sub = wl[wl.bucket == key]
        if not len(sub):
            continue
        rows = "".join(f"<tr><td><b>{html.escape(r.symbol)}</b></td><td>{f(r.last_close)}</td>{plan_cells(r)}</tr>"
                       for r in sub.itertuples())
        imgs = "".join(f'<a href="charts/{s}_45m.png"><img src="charts/{s}_45m.png" alt="{s}"></a>'
                       for s in sub.symbol) if key in ("in_zone", "waiting") else ""
        sections += (f"<h2>{name} · {len(sub)}</h2><p class='muted'>{how}</p><div class='card' style='overflow-x:auto'>"
                     f"<table><tr><th>Stock</th><th>Last</th><th>Entry</th><th>Stop</th><th>T1 / T2</th><th>R:R</th>"
                     f"<th>Qty 1 %</th><th>Quality</th></tr>{rows}</table></div>{imgs}")
    steps = " → ".join(f"{n} {html.escape(t)}" for t, n in res["steps"])
    m = res["market"]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICT watchlist {res['as_of']:%d %b %Y}</title><style>{report.CSS}</style></head><body><main>
<h1>Possible entries · {res['as_of']:%d %b %Y}</h1>
<p class="muted">{steps}{' · WIDE mode (discount, zone and RS filters relaxed)' if wide else ''}</p>
<div class="card"><b>Market:</b> {html.escape(m['sentence'])}</div>
{'' if res['market_ok'] else '<div class="card warn"><b>Market filter blocks new longs.</b> In the walk-forward, trades taken on blocked days averaged −0.29R. Treat this list as study/paper only.</div>'}
<div class="card"><b>{counts['in_zone']}</b> in zone · <b>{counts['waiting']}</b> waiting · <b>{counts['leg_running']}</b> leg running · <b>{counts['setting_up']}</b> setting up</div>
<div class="card"><small>Walk-forward (Feb–Nov 2026, 60m proxy, after costs): all setups −0.14R/trade; A-like setups +0.08R (47 trades, not proven).
Check every chart in TradingView with the ICT Swing Engine indicator before acting. Education only, not financial advice.</small></div>
{sections}</main></body></html>"""
    (out / "index.html").write_text(page)
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="update daily bars and indices first (needs internet)")
    ap.add_argument("--no-fetch-intraday", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--wide", action="store_true")
    ap.add_argument("--no-timemachine", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    if a.fetch:
        subprocess.run([sys.executable, "-m", "scripts.fetch_data", "--daily", "--indices"], cwd=ROOT, check=False)
    cfg = load_config()
    if a.wide:
        c2 = cfg["scan"]["stage2"]
        c2["require_discount"], c2["zone_proximity_atr"], c2["rs_min_pct"] = False, 1e9, 0
    res = run_scan(copy.deepcopy(cfg), a.date, fetch_intraday=not a.no_fetch_intraday, workers=a.workers,
                   watch=True, log=lambda *x: None)
    res["cfg"] = cfg
    wl = build(res, cfg, not a.no_timemachine)
    out = ROOT / "reports" / "daily" / f"{res['as_of']:%Y-%m-%d}{'_wide' if a.wide else ''}"
    counts = write(out, res, wl, a.wide) if len(wl) else {}
    print(res["market"]["sentence"])
    print(" → ".join(f"{n} {t}" for t, n in res["steps"]))
    if counts:
        print(f"\nPossible entries: {counts['in_zone']} in zone · {counts['waiting']} waiting · "
              f"{counts['leg_running']} leg running · {counts['setting_up']} setting up\n")
        show = wl[wl.bucket != "near_miss"]
        for key, name, _ in BUCKETS:
            sub = show[show.bucket == key]
            if not len(sub):
                continue
            print(name)
            for r in sub.itertuples():
                if key in ("in_zone", "waiting"):
                    tm = f" · TM avg {f(getattr(r, 'tm_avg_R_filled', np.nan))}R" if "tm_avg_R_filled" in wl else ""
                    print(f"  {r.symbol:<12} entry {f(r.entry):>10}  stop {f(r.stop):>10}  T1 {f(r.t1):>10}  "
                          f"T2 {f(r.t2):>10}  R:R {f(r.rr_t2)}  {'A-like' if r.a_like else 'B-like'}{tm}")
                elif key == "leg_running":
                    print(f"  {r.symbol:<12} leg {f(r.leg_low)} → {f(r.leg_high)}  provisional OTE {f(r.ote_79)}–{f(r.ote_62)}")
                else:
                    print(f"  {r.symbol:<12} sweep low {f(r.sweep_low)}  trigger: close above {f(r.trigger)} "
                          f"({f(r.dist_to_trigger_atr, 1)} ATR away)")
        print(f"\nOpen: {out / 'index.html'}\nTradingView watchlist: {out / 'tradingview_watchlist.txt'}")
    else:
        print("No stock reached the 45-minute stage today.")


if __name__ == "__main__":
    main()
