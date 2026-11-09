"""Build the ICT concept site into docs/ (GitHub Pages ready).

Usage: python -m scripts.build_site
Needs data/raw/NIFTY.csv (daily) and data/raw/NIFTY_15m.csv (15-minute).
"""
from __future__ import annotations

import re
from datetime import datetime
from html import escape

from ict_engine.config import ROOT, load_config
from ict_engine.data.loader import load_csv, to_weekly
from ict_engine.site import figures as F
from ict_engine.site.content import CONCEPTS, PARTS

DOCS = ROOT / "docs"
REPO = "https://github.com/RakeshDoreswamy/ict-swing-engine"

FIGS = {
    "swings_schematic": lambda d: F.swings_schematic(), "swings_real": F.swings_real,
    "levels_schematic": lambda d: F.levels_schematic(), "levels_real": F.levels_real,
    "open_float_schematic": lambda d: F.open_float_schematic(), "open_float_real": F.open_float_real,
    "pools_schematic": lambda d: F.pools_schematic(), "pools_real": F.pools_real,
    "sweep_schematic": lambda d: F.sweep_schematic(), "sweep_real": F.sweep_real,
    "displacement_schematic": lambda d: F.displacement_schematic(), "displacement_real": F.displacement_real,
    "fvg_schematic": lambda d: F.fvg_schematic(), "fvg_real": F.fvg_real,
    "ob_schematic": lambda d: F.ob_schematic(), "ob_real": F.ob_real,
    "breaker_schematic": lambda d: F.breaker_schematic(), "breaker_real": F.breaker_real,
    "pd_schematic": lambda d: F.pd_schematic(), "pd_real": F.pd_real,
    "ote_schematic": lambda d: F.ote_schematic(), "ote_real": F.ote_real,
    "pd_arrays_real": F.pd_arrays_real,
    "mss_schematic": lambda d: F.mss_schematic(), "mss_real": F.mss_real,
    "mss_real_composite": lambda d: F.mss_real(d, composite=True),
    "progression_flow": lambda d: F.progression_flow(),
    "entries_schematic": lambda d: F.entries_schematic(),
    "management_schematic": lambda d: F.management_schematic(),
    "drawdown_chart": lambda d: F.drawdown_chart(),
    "gaps_real": F.gaps_real, "ipda_real": F.ipda_real, "quarterly_real": F.quarterly_real,
    "seasonal_real": F.seasonal_real, "lookahead_schematic": lambda d: F.lookahead_schematic(),
}

THEME_JS = """<script>
(function(){var r=document.documentElement;try{var t=localStorage.getItem('theme');if(t)r.dataset.theme=t;}catch(e){}
window.toggleTheme=function(){var dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('theme',r.dataset.theme);}catch(e){}};})();
</script>"""


def head(title, css):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)}</title><link rel="stylesheet" href="{css}">{THEME_JS}</head><body>')


def topbar(home):
    return (f'<header class="top"><a class="brand" href="{home}">ICT Swing Engine</a>'
            f'<span class="sp"></span><a href="{REPO}">GitHub</a>'
            f'<button class="navtoggle" onclick="document.querySelector(\'nav.side\').classList.toggle(\'open\')">Concepts</button>'
            f'<button onclick="toggleTheme()" aria-label="Toggle dark mode">◐</button></header>')


def sidebar(active):
    out = ['<nav class="side">']
    for code, name, _ in PARTS:
        out.append(f'<div class="grp"><h4>Part {code} · {escape(name)}</h4>')
        for k, c in enumerate(CONCEPTS, 1):
            if c["part"] == code:
                on = ' class="on"' if c["slug"] == active else ""
                out.append(f'<a{on} href="{c["slug"]}.html"><span class="n">{k}</span>{escape(c["title"])}</a>')
        out.append("</div>")
    out.append("</nav>")
    return "".join(out)


def render_body(body, data):
    html = "".join(body)
    return re.sub(r"\{fig:(\w+)\}", lambda m: FIGS[m.group(1)](data), html)


def page(c, k, data):
    prev_c = CONCEPTS[k - 2] if k > 1 else None
    next_c = CONCEPTS[k] if k < len(CONCEPTS) else None
    status = ('<span class="tag ok">coded · learn command available</span>' if c["status"] == "ok"
              else '<span class="tag plan">explained · code coming</span>')
    part = next(p for p in PARTS if p[0] == c["part"])
    pager = '<div class="pager">'
    pager += (f'<a href="{prev_c["slug"]}.html"><small>← Previous</small>{escape(prev_c["title"])}</a>' if prev_c else "<span></span>")
    pager += (f'<a class="next" href="{next_c["slug"]}.html"><small>Next →</small>{escape(next_c["title"])}</a>' if next_c else "<span></span>")
    pager += "</div>"
    return (head(f'{c["title"]} · ICT concepts', "../assets/site.css") + topbar("../index.html")
            + '<div class="layout">' + sidebar(c["slug"]) + "<main>"
            + f'<div class="crumb">Concept {k} of {len(CONCEPTS)} · Part {part[0]}: {escape(part[1])}</div>'
            + f'<h1>{escape(c["title"])}</h1><p class="lede">{c["lede"]}</p>'
            + f'<div class="tags">{status}<span class="tag">Module {c["module"]}</span></div>'
            + render_body(c["body"], data)
            + '<div class="card"><small>Education only, not financial advice. ICT concepts are not independently proven; '
              "this engine exists to test them. Check current SEBI/exchange rules and consider a SEBI-registered advisor before using real capital.</small></div>"
            + pager + "</main></div></body></html>")


def practice_section():
    pages = sorted(p.parent.name for p in (DOCS / "practice").glob("*/index.html")) if (DOCS / "practice").exists() else []
    if not pages:
        return ""
    tiles = "".join(f'<a class="tile" href="practice/{p}/index.html"><span class="num">PRACTICE</span><b>{p}: all concepts on real data</b>'
                    f'<span>Annotated images: HTF map, live 15m view, concept atlas, complete setups with results.</span></a>' for p in pages)
    return f'<section class="part" style="margin:8px 0 30px"><h2>Practice on real data</h2><p>Every concept marked automatically on an uploaded price file.</p><div class="tiles">{tiles}</div></section>'


def index(data):
    parts = []
    for code, name, blurb in PARTS:
        tiles = "".join(
            f'<a class="tile" href="concepts/{c["slug"]}.html"><span class="num">{k:02d}</span><b>{escape(c["title"])}</b>'
            f'<span>{escape(c["short"])}</span></a>' for k, c in enumerate(CONCEPTS, 1) if c["part"] == code)
        parts.append(f'<section class="part"><h2>Part {code} · {escape(name)}</h2><p>{escape(blurb)}</p><div class="tiles">{tiles}</div></section>')
    m15, dd = data.m15, data.daily
    return (head("ICT Swing Engine · Concepts", "assets/site.css") + topbar("index.html")
            + '<main style="margin:0 auto;max-width:1100px"><div class="hero">'
            + "<h1>ICT swing-trading concepts, explained on real NIFTY charts</h1>"
            + '<p class="lede">25 concepts in learning order. Each page has the idea, the exact rule the engine uses, a diagram, '
              "a real example found automatically in NIFTY data, common mistakes and an exercise.</p>"
            + f'<div class="tags"><span class="tag">NIFTY 15m: {m15.index[0]:%d %b} to {m15.index[-1]:%d %b %Y} ({len(m15)} bars)</span>'
              f'<span class="tag">NIFTY daily: {dd.index[0]:%b %Y} to {dd.index[-1]:%b %Y}</span>'
              f'<span class="tag">Built {datetime.now():%d %b %Y}</span></div></div>'
            + practice_section()
            + '<div class="parts">' + "".join(parts) + "</div>"
            + '<div class="card" style="margin-top:30px"><b>How to study</b><ol><li>Read a page.</li><li>Do its exercise by hand on TradingView.</li>'
              "<li>Run its <code>learn</code> command (where available) and compare.</li><li>Rebuild this site after updating data: "
              "<code>python -m scripts.build_site</code>.</li></ol></div></main></body></html>")


def main():
    cfg = load_config()
    daily = load_csv("NIFTY")
    m15 = load_csv("NIFTY_15m")
    data = F.Data(cfg, m15, daily, to_weekly(daily, cfg["data"]["weekly_rule"]))
    (DOCS / "concepts").mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(index(data))
    for k, c in enumerate(CONCEPTS, 1):
        (DOCS / "concepts" / f'{c["slug"]}.html').write_text(page(c, k, data))
        print(f"  {k:2d} {c['slug']}")
    (DOCS / ".nojekyll").write_text("")
    print(f"Built {len(CONCEPTS)} pages into docs/")


if __name__ == "__main__":
    main()
