"""Charts, CSVs and the HTML page for a scan run (reports/scans/<date>/)."""
from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd

from ict_engine.detectors.swings import swing_table
from ict_engine.viz.mpl import C, Ax, plt


def fmt(x, d=2):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.{d}f}"


def chart(sym: str, m45: pd.DataFrame, r: dict, cfg: dict, path: Path, daily: dict | None = None) -> None:
    r = dict(r)
    for k in ("sweep_bar", "mss_bar", "leg_high_bar", "leg_low_bar"):
        r[k] = int(r[k])   # bar positions can come back as floats after DataFrame merges
    nb = cfg["scan"]["stage4"]["chart_bars"]
    off = max(0, len(m45) - nb)
    df = m45.iloc[off:]
    fig, ax = plt.subplots(figsize=(15, 7.5))
    A = Ax(ax, df, f"{sym} · 45-minute · grade {r['grade']} · {r['state'].replace('_', ' ')} · score {r['score']}",
           "%d %b %H:%M", 9)
    A.day_separators()
    sw = swing_table(m45, cfg)
    for s in sw[sw.bar >= off].itertuples():
        hi = s.side == "high"
        if s.level == 1:
            A.tri(s.bar - off, s.price, C["dn"] if hi else C["up"], not hi)
        else:
            A.mark(s.bar - off, s.price, s.type, C["blue"] if s.level == 2 else C["purple"], above=hi, dy=0.025, fs=7)
    x0 = max(r["sweep_bar"] - off, 0)
    for name, lo, hi_, b in r.get("confluence", []):
        A.zone(max(b - off, 0), None, hi_, lo, C["bull"] if name == "FVG" else C["blue"], f"{name} in OTE", alpha=0.2)
    A.zone(r["leg_high_bar"] - off, None, r["ote_62"], r["ote_79"], C["gold"], None, alpha=0.22)
    A.mark(r["sweep_bar"] - off, m45.low.iloc[r["sweep_bar"]], f"① {r['sweep_type']} sweep", C["teal"], above=False, dy=0.05, marker="D")
    A.hline(r["mss_level"], max(r["mss_bar"] - off - 6, 0), r["mss_bar"] - off, C["blue"], None, ls="-", lw=1.3)
    A.mark(r["mss_bar"] - off, m45.high.iloc[r["mss_bar"]], "② MSS", C["blue"], dy=0.06, marker="*")
    A.mark(r["leg_high_bar"] - off, r["leg_high"], "leg high", C["dn"], dy=0.04, fs=7)
    A.hline(r["entry"], r["leg_high_bar"] - off, None, C["blue"], f"③ entry 70.5% {fmt(r['entry'])}", ls="-", lw=1.5)
    A.hline(r["stop"], x0, None, C["dn"], f"④ stop {fmt(r['stop'])}", ls="-", lw=1.5)
    A.hline(r["t1"], r["leg_high_bar"] - off, None, C["up"], f"⑤ T1 {fmt(r['t1'])} (R:R {fmt(r['rr_t1'])})", ls="--")
    if r["t2"] == r["t2"]:
        A.hline(r["t2"], r["leg_high_bar"] - off, None, C["up"], f"⑥ T2 {fmt(r['t2'])} (R:R {fmt(r['rr_t2'])})", ls="-", lw=1.5)
    A.rtext((r["ote_62"] + r["ote_79"]) / 2, f"OTE {fmt(r['ote_79'])}–{fmt(r['ote_62'])}", C["gold"], 8)
    lo_, hi_ = A.ax.get_ylim()
    for t in ("eq", "range_low", "range_high"):
        v = r.get(t)
        if v == v and v is not None and lo_ <= v <= hi_:
            A.hline(v, 0, None, C["grey"], {"eq": "daily EQ", "range_low": "daily range low", "range_high": "daily range high"}[t] + f" {fmt(v)}", ls=":", lw=0.9)
    conf = ", ".join(z[0] for z in r.get("confluence", [])) or "none"
    A.note(f"Daily: bias {r.get('bias')}, {'discount' if r.get('discount') else 'premium'}, near {r.get('zone') or '—'}  ·  RS pct {fmt(r.get('rs_pct'), 0)}\n"
           f"Confluence in OTE: {conf}  ·  risk {fmt(r['risk'])} pts  ·  qty at 1% of Rs 10L (×1.25 gap pad): {r.get('qty_1pct', 0):,}\n"
           f"Sweep {pd.Timestamp(r['sweep_time']):%d %b %H:%M} → MSS {pd.Timestamp(r['mss_time']):%d %b %H:%M} → wait for a limit fill at 70.5%",
           fs=8.5)
    fig.text(0.01, 0.005, "ICT Swing Engine scanner · education only, not financial advice", fontsize=7.5, color=C["grey"])
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


CSS = """:root{--bg:#fbfaf7;--panel:#fff;--ink:#1d1f23;--muted:#5f6672;--line:#e4e1da;--accent:#2357c6;--up:#1f9d6b;--dn:#d1453b;--gold:#b7791f}
@media (prefers-color-scheme:dark){:root{--bg:#121418;--panel:#1a1d23;--ink:#e8e9ec;--muted:#9aa1ad;--line:#2b2f37;--accent:#7aa2ff;--up:#34c48b;--dn:#ff6b5e;--gold:#e0a84a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 60px}h1{font-size:28px;margin:0 0 6px}.muted{color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.funnel{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.funnel b{font-size:22px}.funnel span{color:var(--muted);font-size:13px}
.step{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;text-align:center}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px 14px;font-size:14px}.grid div span{display:block;color:var(--muted);font-size:12px}
.tag{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:600;margin-left:6px}
.A{background:rgba(31,157,107,.15);color:var(--up)}.B{background:rgba(183,121,31,.15);color:var(--gold)}.C{background:rgba(209,69,59,.12);color:var(--dn)}
img{width:100%;height:auto;border-radius:6px;margin-top:10px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
.warn{border-left:4px solid var(--dn)}"""


def write_html(out: Path, as_of, market: dict, funnel: list, finalists: pd.DataFrame, stage3_all: pd.DataFrame,
               watch_only: bool = False) -> None:
    steps = "".join(f'<div class="step"><b>{n}</b><br><span>{html.escape(t)}</span></div>' + ("<span>→</span>" if i < len(funnel) - 1 else "")
                    for i, (t, n) in enumerate(funnel))
    cards = []
    for r in finalists.itertuples():
        cards.append(f"""<div class="card"><h2 style="margin:0">{html.escape(r.symbol)}<span class="tag {r.grade}">grade {r.grade}</span>
<span class="tag B">{html.escape(r.state.replace('_', ' '))}</span><span class="muted" style="font-size:14px"> · score {r.score}</span></h2>
<div class="grid" style="margin-top:8px"><div><span>Entry (70.5%)</span>{fmt(r.entry)}</div><div><span>Stop</span>{fmt(r.stop)}</div>
<div><span>T1 · R:R</span>{fmt(r.t1)} · {fmt(r.rr_t1)}</div><div><span>T2 · R:R</span>{fmt(r.t2)} · {fmt(r.rr_t2)}</div>
<div><span>OTE band</span>{fmt(r.ote_79)}–{fmt(r.ote_62)}</div><div><span>Last close · distance</span>{fmt(r.last_close)} · {fmt(r.dist_to_entry_atr, 1)} ATR</div>
<div><span>Qty at 1% risk</span>{int(r.qty_1pct):,}</div><div><span>Daily</span>{html.escape(str(r.bias))}, {'discount' if r.discount else 'premium'}, {html.escape(str(r.zone))}</div></div>
<a href="charts/{r.symbol}_45m.png"><img src="charts/{r.symbol}_45m.png" alt="{html.escape(r.symbol)} 45m chart"></a></div>""")
    near = stage3_all[~stage3_all["pass"].astype(bool)].copy() if len(stage3_all) and "pass" in stage3_all else pd.DataFrame()
    rows = "".join(f"<tr><td>{html.escape(str(r.symbol))}</td><td>{html.escape(str(r.state))}</td><td>{html.escape(str(r.reason))}</td></tr>"
                   for r in near.head(60).itertuples()) if len(near) else ""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICT scan {pd.Timestamp(as_of):%d %b %Y}</title><style>{CSS}</style></head><body><main>
<h1>ICT 45-minute OTE scan · {pd.Timestamp(as_of):%d %b %Y}</h1><p class="muted">NSE equities, long side. Every value comes from the engine's rules on closed bars.</p>
<div class="card"><b>Market (stage 0):</b> {html.escape(market['sentence'])}</div>
{'<div class="card warn"><b>WATCH LIST ONLY.</b> The market filter blocks new longs today, so nothing below can be grade A. Use these to learn the setups and to be ready when the market turns.</div>' if watch_only else ''}
<div class="funnel">{steps}</div>
{''.join(cards) if cards else '<div class="card">No stock passed every stage today.</div>'}
<h2>Stage 3 near misses</h2><div class="card" style="overflow-x:auto"><table><tr><th>Symbol</th><th>State</th><th>Why it dropped</th></tr>{rows}</table></div>
<div class="card warn"><small>A limit at 70.5% may never fill; a setup is invalid if price trades below the sweep low first. These are rules-based candidates for study and paper trading, not recommendations. Education only, not financial advice.</small></div>
</main></body></html>"""
    (out / "index.html").write_text(page)
