"""The daily email: subject, HTML body (inline styles for mail clients) and a plain-text fallback."""
from __future__ import annotations

import html as H

import numpy as np
import pandas as pd

BUCKET_LABEL = {"in_zone": "🟢 In zone", "waiting": "🟡 Waiting", "leg_running": "🔵 Leg running",
                "setting_up": "⚪ Setting up"}
CONV_COLOR = {"STRONG": "#1f9d6b", "MODERATE": "#b7791f", "WEAK": "#d1453b"}
S = {  # inline styles
    "body": "margin:0;padding:0;background:#f4f2ee;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d1f23",
    "wrap": "max-width:760px;margin:0 auto;padding:18px 14px",
    "card": "background:#ffffff;border:1px solid #e4e1da;border-radius:10px;padding:14px 16px;margin:12px 0",
    "h2": "font-size:17px;margin:20px 0 6px",
    "muted": "color:#5f6672;font-size:13px",
    "th": "text-align:left;padding:5px 8px;border-bottom:1px solid #e4e1da;color:#5f6672;font-size:12px",
    "td": "padding:5px 8px;border-bottom:1px solid #eeebe5;font-size:13px;vertical-align:top",
}


def f(x, d=2):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.{d}f}"


def dur(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def subject(as_of, market_ok: bool, counts: dict, conv: dict, seconds: float, mode: str) -> str:
    status = "ACTIVE" if market_ok else "WATCH-ONLY"
    return (f"NSE ICT Screener [{status}] {pd.Timestamp(as_of):%Y-%m-%d} — {counts.get('in_zone', 0)} IN ZONE + "
            f"{counts.get('waiting', 0)} WAITING + {counts.get('leg_running', 0)} LEG RUNNING + "
            f"{counts.get('setting_up', 0)} SETTING UP | {conv.get('STRONG', 0)} STRONG · {conv.get('MODERATE', 0)} MODERATE"
            f" | 5-Stage ICT Framework{' (wide)' if mode != 'base' else ''} | Scan {dur(seconds)}")


def _table(head, rows):
    th = "".join(f'<th style="{S["th"]}">{h}</th>' for h in head)
    tr = "".join("<tr>" + "".join(f'<td style="{S["td"]}">{c}</td>' for c in r) + "</tr>" for r in rows)
    return f'<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%">{"<tr>" + th + "</tr>"}{tr}</table>'


def _names(sub: pd.DataFrame, n=8) -> str:
    s = sub.symbol.tolist()
    return ", ".join(s[:n]) + (f", … (+{len(s) - n})" if len(s) > n else "")


def funnel_rows(info: dict) -> list:
    rows = [["Scanned (NSE EQ/BE universe)", f"<b>{info['universe']:,}</b>", ""],
            ["Stage 0 · market", "longs allowed" if info["market_ok"] else "<b style='color:#d1453b'>longs blocked</b>",
             H.escape(info["market_sentence"])],
            ["Stage 1 · liquid & tradeable", f"<b>{info['s1_pass']:,}</b>",
             f"{info['universe'] - info['s1_pass']:,} dropped: " + H.escape(info["s1_top"])],
            ["Stage 2 · daily ICT context (base rules)", f"<b>{info['s2_base']:,}</b>", H.escape(info["s2_top"])]]
    if info.get("s2_wide") is not None:
        rows.append(["Stage 2 · wide mode (discount, zone, RS relaxed)", f"<b>{info['s2_wide']:,}</b>", "study list"])
    rows.append(["Stage 3 · 45-minute ICT setups", f"<b>{info['setups']:,}</b>",
                 f"{info['near_miss']:,} near misses (no 45m setup)"])
    return rows


def candidate_card(r: dict, cid_chart: str | None, cid_fan: str | None, tm: dict | None) -> str:
    conv = r["conviction"]
    badge = (f'<span style="background:{CONV_COLOR[conv]};color:#fff;border-radius:999px;padding:2px 9px;'
             f'font-size:12px;font-weight:700">{conv}</span>')
    tags = f'{BUCKET_LABEL.get(r["bucket"], r["bucket"])} · {"A-like" if r["a_like"] else "B-like"} · ' \
           f'{"base rules" if r.get("base_rules") else "wide only"}'
    risk = r["entry"] - r["stop"]
    plan = _table(["Entry (limit 70.5 %)", "Stop", "Risk / share", "T1", "T2", "R:R T2", "Qty @1 % of Rs 10L", "Costs"],
                  [[f"<b>{f(r['entry'])}</b>", f(r["stop"]), f"{f(risk)} ({risk / r['entry'] * 100:.1f} %)",
                    f(r["t1"]), f(r["t2"]), f(r.get("rr_t2")), f"{int(r.get('qty_1pct') or 0):,}", f"{f(r.get('cost_R'))}R"]])
    tmh = ""
    if tm:
        oc = tm["outcomes_pct"]
        parts = " · ".join(f"{k} {v:.1f} %" for k, v in sorted(oc.items(), key=lambda kv: -kv[1]))
        tmh = (f'<div style="margin-top:8px"><b>Time Machine</b> <span style="{S["muted"]}">({tm["config"]["replays"]:,} replays of '
               f'the next {tm["config"]["days"]} sessions from {tm["pool"]["sessions"]} real sessions, volatility ×{tm["pool"]["vol_scale"]})</span><br>'
               f'Fill {tm["fill_rate_pct"]} % · win when filled {tm["win_rate_filled_pct"]} % · '
               f'<b>avg {tm["avg_R_filled"]:+.2f}R when filled</b> (after costs) · median exit session {tm["median_exit_session"]} · '
               f'close after {tm["config"]["days"]} sessions {f(tm["end_price"]["median"])} (90 %: {f(tm["end_price"]["p5"])}–{f(tm["end_price"]["p95"])})'
               f'<br><span style="{S["muted"]}">{H.escape(parts)}</span><br><i>{H.escape(tm["verdict"])}</i></div>')
    pros = "".join(f"<li>✔ {H.escape(p)}</li>" for p in r["pros"])
    cons = "".join(f"<li>✘ {H.escape(c)}</li>" for c in r["cons"])
    imgs = ""
    if cid_chart:
        imgs += f'<img src="cid:{cid_chart}" alt="{r["symbol"]} 45m chart" style="width:100%;max-width:728px;border-radius:6px;margin-top:10px">'
    if cid_fan:
        imgs += f'<img src="cid:{cid_fan}" alt="{r["symbol"]} Time Machine" style="width:100%;max-width:728px;border-radius:6px;margin-top:6px">'
    return (f'<div style="{S["card"]}"><div style="font-size:18px;font-weight:700">{H.escape(r["symbol"])} {badge}</div>'
            f'<div style="{S["muted"]}">{tags} · last close {f(r.get("last_close"))} · OTE {f(r.get("ote_79"))}–{f(r.get("ote_62"))}</div>'
            f'<div style="margin-top:8px">{plan}</div>{tmh}'
            f'<div style="margin-top:8px"><b>Why it qualifies</b><ul style="margin:4px 0 0 18px;padding:0;font-size:13px">{pros}</ul></div>'
            f'<div style="margin-top:6px"><b>Against it</b><ul style="margin:4px 0 0 18px;padding:0;font-size:13px">{cons or "<li>nothing flagged</li>"}</ul></div>'
            f'{imgs}</div>')


def body(info: dict, wl: pd.DataFrame, details: dict, wf_lines: list[str]) -> tuple[str, str, dict]:
    """Returns (html, text, inline images {cid_key: path})."""
    inline = {}
    counts = info["counts"]
    summary = _table(["Bucket", "Stocks", "Names"], [
        [BUCKET_LABEL[k], f"<b>{counts.get(k, 0)}</b>", H.escape(_names(wl[wl.bucket == k]))] for k in BUCKET_LABEL])
    plans = wl[wl.bucket.isin(["in_zone", "waiting"])]
    cards = ""
    compact = []
    for r in plans.to_dict("records"):
        d = details.get(r["symbol"])
        if d:
            ck, fk = f"chart_{r['symbol']}", f"fan_{r['symbol']}"
            inline[ck], inline[fk] = d["chart"], d["fan"]
            cards += candidate_card(r, ck, fk, d["tm"])
        else:
            compact.append([f"<b>{H.escape(r['symbol'])}</b>", BUCKET_LABEL[r["bucket"]], r["conviction"],
                            f(r["entry"]), f(r["stop"]), f(r["t1"]), f(r.get("rr_t2")),
                            f(r.get("tm_avg_R_filled")), "A" if r["a_like"] else "B",
                            H.escape("; ".join(r["cons"][:2]))])
    rest = (f'<h2 style="{S["h2"]}">Other plans ({len(compact)})</h2><div style="{S["card"]}">' +
            _table(["Stock", "Bucket", "Conviction", "Entry", "Stop", "T1", "R:R", "TM avg R", "A/B", "Main concerns"], compact)
            + "</div>") if compact else ""
    lr = wl[wl.bucket == "leg_running"]
    su = wl[wl.bucket == "setting_up"]
    lr_t = _table(["Stock", "Leg low → high", "Provisional OTE"], [[H.escape(r.symbol), f"{f(r.leg_low)} → {f(r.leg_high)}",
                                                                   f"{f(r.ote_79)}–{f(r.ote_62)}"] for r in lr.itertuples()]) if len(lr) else ""
    su_t = _table(["Stock", "Sweep low", "Trigger (close above)", "Distance"],
                  [[H.escape(r.symbol), f(r.sweep_low), f"<b>{f(r.trigger)}</b>", f"{f(r.dist_to_trigger_atr, 1)} ATR"]
                   for r in su.itertuples()]) if len(su) else ""
    status = "ACTIVE" if info["market_ok"] else "WATCH-ONLY"
    wf = "".join(f"<li>{H.escape(x)}</li>" for x in wf_lines)
    html = f"""<!doctype html><html><body style="{S['body']}"><div style="{S['wrap']}">
<div style="font-size:22px;font-weight:800">NSE ICT Screener · {pd.Timestamp(info['as_of']):%a %d %b %Y}
<span style="font-size:13px;background:{'#1f9d6b' if info['market_ok'] else '#d1453b'};color:#fff;border-radius:6px;padding:2px 8px;vertical-align:middle">{status}</span></div>
<div style="{S['muted']}">5-stage ICT framework: market → universe → daily ICT → 45-minute sweep/MSS/OTE → rank + Time Machine · scan time {dur(info['seconds'])}</div>
{'' if info['market_ok'] else f'<div style="{S["card"]};border-left:4px solid #d1453b"><b>Watch-only day.</b> The market filter blocks new longs. Use the list to study and prepare; in the walk-forward, trades on blocked days averaged −0.29R.</div>'}
<h2 style="{S['h2']}">Funnel</h2><div style="{S['card']}">{_table(['Stage', 'Stocks', 'Notes'], funnel_rows(info))}</div>
<h2 style="{S['h2']}">Buckets</h2><div style="{S['card']}">{summary}</div>
<h2 style="{S['h2']}">Buy candidates: full detail (sorted by bucket, conviction, Time Machine)</h2>
{cards or f'<div style="{S["card"]}">No stock is in zone or waiting today.</div>'}
{rest}
{f'<h2 style="{S["h2"]}">🔵 Leg running ({len(lr)}): wait for the rally to stop</h2><div style="{S["card"]}">{lr_t}</div>' if len(lr) else ''}
{f'<h2 style="{S["h2"]}">⚪ Setting up ({len(su)}): alert for a close above the trigger</h2><div style="{S["card"]}">{su_t}</div>' if len(su) else ''}
<h2 style="{S['h2']}">What the evidence says so far</h2><div style="{S['card']}"><ul style="margin:0 0 0 18px;padding:0;font-size:13px">{wf}</ul></div>
<div style="{S['muted']};margin-top:14px">How to use: import the attached tradingview_watchlist.txt in TradingView (Watchlist → ⋯ → Import list),
open each stock on the 45-minute chart with the ICT Swing Engine indicator, and confirm the sweep, MSS, OTE band and levels by eye.
Rules-based screening for study and paper trading. Not investment advice; not a recommendation to buy or sell. Check results dates and news before acting.</div>
</div></body></html>"""
    text = [f"NSE ICT Screener [{status}] {pd.Timestamp(info['as_of']):%Y-%m-%d}", info["market_sentence"], ""]
    text += [f"{BUCKET_LABEL[k]}: {counts.get(k, 0)} ({_names(wl[wl.bucket == k])})" for k in BUCKET_LABEL]
    text += ["", "Buy candidates:"]
    for r in plans.to_dict("records"):
        text.append(f"  {r['symbol']:<12} {r['bucket']:<8} {r['conviction']:<8} entry {f(r['entry'])} stop {f(r['stop'])} "
                    f"T1 {f(r['t1'])} T2 {f(r['t2'])} TM {f(r.get('tm_avg_R_filled'))}R")
    text += ["", "Education only, not financial advice."]
    return html, "\n".join(text), inline
