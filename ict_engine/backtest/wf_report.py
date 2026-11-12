"""HTML + charts for a walk-forward run."""
from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd

from ict_engine.viz.mpl import C, plt

LABELS = {"base": "Base (all filters)", "no_market_filter": "Without the market filter",
          "no_rs_filter": "Without relative strength", "no_zone_filter": "Without daily-zone proximity",
          "no_room_filter": "Without the room-to-target rule", "require_confluence": "Base + FVG/OB confluence required"}


def _equity_png(results: dict, path: Path):
    fig, ax = plt.subplots(figsize=(12, 5))
    for name, t in results.items():
        if len(t) and t["R"].notna().any():
            tt = t[t["R"].notna()].sort_values("fill_time")
            ax.plot(pd.to_datetime(tt.fill_time), tt["R"].cumsum(), lw=2.2 if name == "base" else 1.1,
                    label=LABELS.get(name, name), color=C["blue"] if name == "base" else None)
    ax.axhline(0, color=C["grey"], lw=0.8)
    ax.set_ylabel("cumulative R (after costs)")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="y", color="#eeebe5")
    ax.set_title("Equity in R by rule set", loc="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _hist_png(t: pd.DataFrame, path: Path):
    r = t["R"].dropna()
    fig, ax = plt.subplots(figsize=(8, 4))
    if len(r):
        bins = np.arange(np.floor(r.min() * 2) / 2 - 0.25, np.ceil(r.max() * 2) / 2 + 0.5, 0.5)
        ax.hist(r, bins=bins, color=[C["up"]], edgecolor="white")
        ax.axvline(r.mean(), color=C["blue"], lw=1.5, ls="--", label=f"average {r.mean():+.2f}R")
        ax.legend(fontsize=8)
    ax.set_title("Base: distribution of trade results (R)", loc="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _table(d: dict, first="Rule set") -> str:
    cols = ["trades", "fill_rate_pct", "win_rate_pct", "avg_R", "total_R", "profit_factor", "max_drawdown_R",
            "max_losing_streak", "avg_cost_R"]
    head = "".join(f"<th>{c.replace('_', ' ')}</th>" for c in cols)
    rows = ""
    for k, m in d.items():
        cells = "".join(f"<td>{m.get(c, '—')}</td>" for c in cols)
        rows += f"<tr><td><b>{html.escape(LABELS.get(k, k))}</b></td>{cells}</tr>"
    return f"<table><tr><th>{first}</th>{head}</tr>{rows}</table>"


def write(out: Path, s: dict, results: dict):
    _equity_png(results, out / "equity.png")
    _hist_png(results["base"], out / "hist.png")
    base = s["rule_sets"]["base"]
    n = base.get("trades", 0)
    verdict = ("Too few trades to judge (need 30+)." if n < 30 else
               "Positive after costs on this sample." if base.get("avg_R", 0) > 0 else "Negative after costs on this sample.")
    proxy = ("<p><b>Timeframe note:</b> 60-minute candles stand in for 45-minute ones because Yahoo keeps only 60 days of "
             "15-minute data. The rules are identical; candle size differs.</p>" if s["timeframe"] == "60m" else "")
    extra = ""
    for key, title in (("base_by_grade", "Base by setup quality"), ("market_ok_vs_blocked", "Market filter: allowed vs blocked days"),
                       ("base_by_month", "Base by month")):
        if key in s:
            extra += f"<h2>{title}</h2><div class='card' style='overflow-x:auto'>{_table(s[key], 'Group')}</div>"
    trades = results["base"]
    rows = "".join(
        f"<tr><td>{html.escape(str(r.symbol))}</td><td>{pd.Timestamp(r.scan_date):%d %b %y}</td><td>{r.entry:,.2f}</td>"
        f"<td>{r.stop:,.2f}</td><td>{r.t1:,.2f}</td><td>{'' if r.t2 != r.t2 else f'{r.t2:,.2f}'}</td>"
        f"<td>{html.escape(str(r.result))}</td><td>{'' if r.R != r.R else f'{r.R:+.2f}'}</td></tr>"
        for r in trades.sort_values("scan_date").itertuples()) if len(trades) else ""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICT scanner walk-forward</title><style>
:root{{--bg:#fbfaf7;--panel:#fff;--ink:#1d1f23;--muted:#5f6672;--line:#e4e1da;--dn:#d1453b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121418;--panel:#1a1d23;--ink:#e8e9ec;--muted:#9aa1ad;--line:#2b2f37;--dn:#ff6b5e}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,sans-serif}}main{{max-width:1150px;margin:0 auto;padding:24px 16px 60px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}}.warn{{border-left:4px solid var(--dn)}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--muted);font-size:12px}}
img{{width:100%;height:auto;border-radius:6px}}.muted{{color:var(--muted)}}</style></head><body><main>
<h1>ICT scanner walk-forward · {s['timeframe']} · {s['test_start']} → {s['test_end']}</h1>
<p class="muted">{s['scan_days']} scan days · {s['symbols_with_data']} symbols with intraday data · round-trip costs {s['cost_pct_round_trip']}% of price, subtracted in R</p>
<div class="card"><b>Verdict for the base rules:</b> {n} trades, average {base.get('avg_R', '—')}R, total {base.get('total_R', '—')}R. {verdict}{proxy}</div>
<h2>Rule sets (ablation)</h2><div class="card" style="overflow-x:auto">{_table(s['rule_sets'])}</div>
<div class="card"><img src="equity.png" alt="Equity curves"></div><div class="card"><img src="hist.png" alt="R distribution"></div>
{extra}
<h2>Base trades</h2><div class="card" style="overflow-x:auto"><table><tr><th>Symbol</th><th>Scan</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th><th>Result</th><th>R</th></tr>{rows}</table></div>
<div class="card warn"><small>How to read this: an ablation that does <i>better</i> without a filter means that filter is not adding edge on this sample.
Results are in-sample for the rule choices, on free data, with simplified fills. Treat them as a test of the ICT hypotheses, not a forecast. Education only, not financial advice.</small></div>
</main></body></html>"""
    (out / "index.html").write_text(page)
