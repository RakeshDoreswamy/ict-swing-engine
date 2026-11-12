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


def fetch_h1(res) -> None:
    """60m history (Yahoo, up to 730 days) for today's buy candidates, so the Time Machine has a deep pool.
    Missing symbols get the full history; cached ones a 60-day top-up."""
    from ict_engine.data.providers import yahoo
    s3, store = res["stage3"], res["store"]
    if s3 is None or not len(s3):
        return
    syms = s3.loc[s3["state"].isin(["in_zone", "waiting"]), "symbol"].tolist()
    new = [s for s in syms if store.read_series("h1", s) is None]
    old = [s for s in syms if s not in new]
    for group, period in ((new, "730d"), (old, "60d")):
        if group:
            try:
                for sym, df in yahoo.intraday(group, "60m", period).items():
                    store.merge_series("h1", sym, df)
            except Exception as e:  # the Time Machine falls back to 45m bars
                print(f"  60m download failed ({e}); Time Machine uses 45m bars where 60m is missing.")


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


def funnel_info(res_base, res, wl, market_ok, seconds, wide) -> dict:
    s1 = res_base["stage1"]
    top1 = s1[~s1["pass"]].reason.value_counts().head(3)
    s2 = res_base["stage2"]
    top2 = (s2[~s2["pass"]].reason.str.replace(r"[\d.]+ ATR away", "N ATR away", regex=True)
            .str.replace(r"relative strength \d+ pct.*", "weak relative strength", regex=True).value_counts().head(3)) if len(s2) else pd.Series(dtype=int)
    counts = {k: int((wl.bucket == k).sum()) for k, _, _ in BUCKETS} if len(wl) else {}
    return {"as_of": res["as_of"], "market_ok": market_ok, "market_sentence": res["market"]["sentence"],
            "universe": res["steps"][0][1] if res["steps"] else 0, "s1_pass": int(s1["pass"].sum()),
            "s1_top": "; ".join(f"{k} ({v})" for k, v in top1.items()),
            "s2_base": int(s2["pass"].sum()) if len(s2) else 0,
            "s2_top": "dropped: " + "; ".join(f"{k} ({v})" for k, v in top2.items()) if len(top2) else "",
            "s2_wide": int(res["stage2"]["pass"].sum()) if wide and len(res["stage2"]) else None,
            "setups": int(sum(counts.values())), "near_miss": int((wl.bucket == "near_miss").sum()) if len(wl) else 0,
            "counts": counts, "seconds": seconds}


def walkforward_lines() -> list[str]:
    import json
    runs = sorted((ROOT / "reports" / "walkforward").glob("*/summary.json"))
    if not runs:
        return ["No walk-forward run yet."]
    s = json.loads(runs[-1].read_text())
    rs = s["rule_sets"]
    out = [f"Walk-forward {s['test_start']} → {s['test_end']} ({s['timeframe']} candles as a 45m proxy, after Indian delivery costs):"]
    for k, label in (("base", "all base-rule setups"), ("a_like_only", "A-like setups only"),
                     ("a_like_no_zone", "A-like without the zone filter"), ("no_market_filter", "ignoring the market filter")):
        m = rs.get(k)
        if m and m.get("trades"):
            out.append(f"{label}: {m['trades']} trades, win {m['win_rate_pct']} %, average {m['avg_R']:+.2f}R, "
                       f"profit factor {m['profit_factor']}")
    out.append("Small samples: none of this is proven edge yet. Paper trade and log results in R before using real money.")
    return out


def main():
    import time

    from ict_engine.backtest.walkforward import cost_pct
    from ict_engine.notify import daily_email, mailer
    from ict_engine.scan.reasons import scrutinise
    from ict_engine.sim import timemachine as TM

    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="update daily bars and indices first (needs internet)")
    ap.add_argument("--no-fetch-intraday", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--mode", choices=["base", "wide", "both"], default="both",
                    help="base = tested rules only; wide = relaxed daily filters; both = wide list, base names flagged")
    ap.add_argument("--wide", action="store_true", help="same as --mode wide")
    ap.add_argument("--no-timemachine", action="store_true")
    ap.add_argument("--detail", type=int, default=6, help="buy candidates that get charts + a full Time Machine")
    ap.add_argument("--email", action="store_true", help="send the email (settings in .env)")
    ap.add_argument("--email-preview", action="store_true", help="write email.html without sending")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--require-today", action="store_true",
                    help="unattended runs: exit quietly if NSE did not trade today, fail if today's bars are missing")
    a = ap.parse_args()
    mode = "wide" if a.wide else a.mode
    t0 = time.time()
    if a.fetch:
        subprocess.run([sys.executable, "-m", "scripts.fetch_data", "--daily", "--indices"], cwd=ROOT, check=False)
    cfg = load_config()
    if a.require_today and not a.date:
        from ict_engine.data import freshness
        from ict_engine.data.store import Store
        st = Store(cfg["scan"]["store_dir"])
        idx, panel = st.read_series("index", "nifty50"), st.read_daily_panel()
        state, msg = freshness.status(panel.date.max() if len(panel) else None,
                                      idx.index.max() if idx is not None else None, freshness.today_ist())
        print(msg)
        if state == "closed":
            return
        if state == "stale":
            raise SystemExit(1)
    quiet = lambda *x: None  # noqa: E731
    res_base = run_scan(copy.deepcopy(cfg), a.date, fetch_intraday=not a.no_fetch_intraday, workers=a.workers,
                        watch=True, log=quiet)
    res = res_base
    if mode in ("wide", "both"):
        cw = copy.deepcopy(cfg)
        c2 = cw["scan"]["stage2"]
        c2["require_discount"], c2["zone_proximity_atr"], c2["rs_min_pct"] = False, 1e9, 0
        res = run_scan(cw, a.date, fetch_intraday=not a.no_fetch_intraday, workers=a.workers, watch=True, log=quiet)
    res["cfg"] = cfg
    base_syms = set(res_base["stage2"].loc[res_base["stage2"]["pass"], "symbol"]) if len(res_base["stage2"]) else set()
    if not a.no_fetch_intraday and not a.no_timemachine:
        fetch_h1(res)
    wl = build(res, cfg, not a.no_timemachine)
    if len(wl):
        wl["base_rules"] = wl.symbol.isin(base_syms)
        cp = cost_pct(cfg)
        recs = []
        for r in wl.to_dict("records"):
            if r["bucket"] in ("in_zone", "waiting"):
                r.update(scrutinise(r, res["market_ok"], cp))
            recs.append(r)
        wl = pd.DataFrame(recs)
        rank_c = {"STRONG": 0, "MODERATE": 1, "WEAK": 2}
        order = {b[0]: i for i, b in enumerate(BUCKETS)} | {"near_miss": 9}
        wl["_b"] = wl.bucket.map(order)
        wl["_c"] = wl.get("conviction", pd.Series(index=wl.index, dtype=object)).map(rank_c).fillna(3)
        wl["_base"] = ~wl.base_rules
        wl["_tm"] = -pd.to_numeric(wl.get("tm_avg_R_filled", pd.Series(np.nan, index=wl.index)), errors="coerce").fillna(-9)
        wl = wl.sort_values(["_b", "_c", "_base", "_tm"]).drop(columns=["_b", "_c", "_base", "_tm"]).reset_index(drop=True)
    out = ROOT / "reports" / "daily" / f"{res['as_of']:%Y-%m-%d}{'' if mode == 'base' else '_' + mode}"
    counts = write(out, res, wl, mode != "base") if len(wl) else {}
    seconds = time.time() - t0
    print(res["market"]["sentence"])
    print(" → ".join(f"{n} {t}" for t, n in res["steps"]))
    if counts:
        print(f"\nPossible entries: {counts['in_zone']} in zone · {counts['waiting']} waiting · "
              f"{counts['leg_running']} leg running · {counts['setting_up']} setting up")
        for r in wl[wl.bucket.isin(["in_zone", "waiting"])].itertuples():
            print(f"  {r.symbol:<12} {r.bucket:<8} {r.conviction:<8} entry {f(r.entry):>10} stop {f(r.stop):>10} "
                  f"T1 {f(r.t1):>10} R:R {f(r.rr_t2)} TM {f(getattr(r, 'tm_avg_R_filled', np.nan))}R "
                  f"{'A' if r.a_like else 'B'}{'' if r.base_rules else ' (wide)'}")
        print(f"\nOpen: {out / 'index.html'}")
    if not (a.email or a.email_preview):
        return
    # full Time Machine + charts for the top buy candidates
    details = {}
    plans = wl[wl.bucket.isin(["in_zone", "waiting"])].head(a.detail) if len(wl) else wl
    wf = cfg["walkforward"]
    for r in plans.to_dict("records"):
        sym = r["symbol"]
        b = res["store"].read_series("h1", sym)
        per = 7
        if b is None:
            b, per = res["m45"][sym], 8
        else:
            b = b[b.index <= res["end"]]
        try:
            tm = TM.run(b, TM.Plan(sym, r["entry"], r["stop"], r["t1"], r["t2"], float(b.close.iloc[-1])),
                        TM.TMConfig(replays=5000, valid_sessions=wf["order_valid_sessions"], hold_days=wf["hold_days"],
                                    partial=wf["partial_at_t1"], cost_pct=cost_pct(cfg), atr_bars=10 * per))
        except Exception as e:
            print(f"  Time Machine skipped for {sym}: {e}")
            continue
        fan = out / "charts" / f"{sym}_timemachine.png"
        TM.fan_png(tm, fan, f"{sym}: Time Machine, {tm['config']['fan_paths']:,} replays")
        details[sym] = {"tm": tm, "fan": fan, "chart": out / "charts" / f"{sym}_45m.png"}
    # re-scrutinise the detailed candidates with the 5,000-replay Time Machine numbers shown in their cards
    if details:
        cp = cost_pct(cfg)
        for i, r in wl[wl.symbol.isin(list(details))].iterrows():
            tm = details[r.symbol]["tm"]
            upd = dict(r, tm_avg_R_filled=tm["avg_R_filled"], tm_fill_pct=tm["fill_rate_pct"], tm_win_pct=tm["win_rate_filled_pct"])
            upd.update(scrutinise(upd, res["market_ok"], cp))
            for k in ("tm_avg_R_filled", "tm_fill_pct", "tm_win_pct", "conviction", "pros", "cons", "a_like", "cost_R"):
                wl.at[i, k] = upd[k]
    info = funnel_info(res_base, res, wl, res["market_ok"], seconds, mode != "base")
    conv = wl.get("conviction", pd.Series(dtype=object)).value_counts().to_dict() if len(wl) else {}
    subj = daily_email.subject(res["as_of"], res["market_ok"], info["counts"], conv, seconds, mode)
    html_body, text, inline = daily_email.body(info, wl, details, walkforward_lines())
    env = mailer.load_env()
    to = [x.strip() for x in env.get("EMAIL_TO", "").split(",") if x.strip()]
    sender = env.get("GMAIL_USER", "me@example.com")
    msg = mailer.build_message(subj, html_body, text, sender, to or [sender], inline,
                               [out / "watchlist.csv", out / "tradingview_watchlist.txt"],
                               env.get("EMAIL_FROM_NAME", "NSE ICT Screener"))
    preview = out / "email.html"
    ph = html_body
    for k, p in inline.items():
        ph = ph.replace(f"cid:{k}", f"charts/{p.name}")
    preview.write_text(ph)
    (out / "email.eml").write_bytes(bytes(msg))
    print(f"\nSubject: {subj}\nEmail preview: {preview}")
    if a.email:
        if not to:
            raise SystemExit("Email not sent: add EMAIL_TO=a@x.com,b@y.com to .env")
        mailer.send(msg, env)
        print(f"Email sent to {len(to)} recipient(s).")


if __name__ == "__main__":
    main()
