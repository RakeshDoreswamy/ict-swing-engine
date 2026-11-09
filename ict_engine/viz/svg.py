"""Tiny dependency-free SVG candlestick renderer used by the concept site.

Colours come from CSS classes (see docs/assets/site.css) so charts follow light/dark mode.
"""
from __future__ import annotations

from html import escape

import pandas as pd


class Chart:
    def __init__(self, df: pd.DataFrame, width=960, height=360, pad=(18, 170, 28, 58), date_fmt="%d %b",
                 ylim: tuple[float, float] | None = None):
        self.df = df
        self.w, self.h = width, height
        self.pt, self.pr, self.pb, self.pl = pad
        lo, hi = ylim or (df["low"].min(), df["high"].max())
        span = hi - lo or 1
        self.lo, self.hi = lo - span * 0.06, hi + span * 0.06
        self.n = len(df)
        self.step = (self.w - self.pl - self.pr) / max(self.n, 1)
        self.date_fmt = date_fmt
        self.layers: list[str] = []
        self.top_layers: list[str] = []

    # coordinates -------------------------------------------------------------
    def x(self, i: float) -> float:
        return self.pl + (i + 0.5) * self.step

    def y(self, p: float) -> float:
        return self.pt + (self.hi - p) / (self.hi - self.lo) * (self.h - self.pt - self.pb)

    def pos(self, ts) -> int:
        return int(self.df.index.get_indexer([pd.Timestamp(ts)], method="nearest")[0])

    # primitives --------------------------------------------------------------
    def zone(self, i0, i1, top, bot, cls="z-bull", label=None, label_side="left"):
        x0, x1 = self.x(i0) - self.step / 2, self.x(min(i1, self.n - 1)) + self.step / 2
        y0, y1 = self.y(top), self.y(bot)
        self.layers.append(f'<rect class="{cls}" x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{max(y1 - y0, 1):.1f}"/>')
        if label:
            tx = x0 + 4 if label_side == "left" else x1 - 4
            anchor = "start" if label_side == "left" else "end"
            ly = y0 - 4 if y0 > self.pt + 14 else y0 + 13
            self.top_layers.append(f'<text class="lbl {cls}-t" x="{tx:.1f}" y="{ly:.1f}" text-anchor="{anchor}">{escape(label)}</text>')

    def hline(self, price, i0=0, i1=None, cls="lv", label=None, dash=True):
        i1 = self.n - 1 if i1 is None else i1
        x0, x1, yy = self.x(i0) - self.step / 2, self.x(i1) + self.step / 2, self.y(price)
        d = ' stroke-dasharray="4 3"' if dash else ""
        self.layers.append(f'<line class="{cls}" x1="{x0:.1f}" x2="{x1:.1f}" y1="{yy:.1f}" y2="{yy:.1f}"{d}/>')
        if label:
            self.top_layers.append(f'<text class="lbl {cls}-t" x="{x1 + 4:.1f}" y="{yy + 4:.1f}">{escape(label)}</text>')

    def mark(self, i, price, text, cls="m-hi", above=True, offset=14):
        xx, yy = self.x(i), self.y(price)
        ty = yy - offset if above else yy + offset + 8
        self.top_layers.append(
            f'<line class="{cls}" x1="{xx:.1f}" x2="{xx:.1f}" y1="{yy:.1f}" y2="{ty + (6 if above else -10):.1f}"/>'
            f'<text class="lbl {cls}-t" x="{xx:.1f}" y="{ty:.1f}" text-anchor="middle">{escape(text)}</text>')

    def arrow(self, i0, p0, i1, p1, cls="arr", text=None):
        x0, y0, x1, y1 = self.x(i0), self.y(p0), self.x(i1), self.y(p1)
        self.top_layers.append(f'<line class="{cls}" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" marker-end="url(#ah)"/>')
        if text:
            self.top_layers.append(f'<text class="lbl {cls}-t" x="{(x0 + x1) / 2 + 6:.1f}" y="{(y0 + y1) / 2:.1f}">{escape(text)}</text>')

    def highlight(self, i, cls="hl"):
        x0 = self.x(i) - self.step / 2
        self.layers.append(f'<rect class="{cls}" x="{x0:.1f}" y="{self.pt}" width="{self.step:.1f}" height="{self.h - self.pt - self.pb}"/>')

    def note(self, text, x=None, y=None, cls="note"):
        x = self.pl + 6 if x is None else x
        y = self.pt + 14 if y is None else y
        self.top_layers.append(f'<text class="lbl {cls}" x="{x}" y="{y}">{escape(text)}</text>')

    # render ------------------------------------------------------------------
    def _axes(self) -> str:
        out = []
        ticks = 5
        for k in range(ticks + 1):
            p = self.lo + (self.hi - self.lo) * k / ticks
            yy = self.y(p)
            out.append(f'<line class="grid" x1="{self.pl}" x2="{self.w - self.pr}" y1="{yy:.1f}" y2="{yy:.1f}"/>'
                       f'<text class="ax" x="{self.pl - 6}" y="{yy + 4:.1f}" text-anchor="end">{p:,.0f}</text>')
        if self.date_fmt and isinstance(self.df.index, pd.DatetimeIndex):
            every = max(1, -(-self.n // 7))
            for i in range(0, self.n, every):
                out.append(f'<text class="ax" x="{self.x(i):.1f}" y="{self.h - 8}" text-anchor="middle">'
                           f'{self.df.index[i].strftime(self.date_fmt)}</text>')
        return "".join(out)

    def _candles(self) -> str:
        bw = max(self.step * 0.62, 1.2)
        out = []
        for i, r in enumerate(self.df.itertuples()):
            up = r.close >= r.open
            cls = "c-up" if up else "c-dn"
            xx = self.x(i)
            yt, yb = self.y(max(r.open, r.close)), self.y(min(r.open, r.close))
            out.append(f'<line class="{cls}" x1="{xx:.1f}" x2="{xx:.1f}" y1="{self.y(r.high):.1f}" y2="{self.y(r.low):.1f}"/>'
                       f'<rect class="{cls}" x="{xx - bw / 2:.1f}" y="{yt:.1f}" width="{bw:.1f}" height="{max(yb - yt, 0.8):.1f}"/>')
        return "".join(out)

    def svg(self, title="") -> str:
        return (f'<svg class="chart" viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(title)}">'
                '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                '<path d="M0,0 L10,5 L0,10 z" class="ah"/></marker></defs>'
                f'{self._axes()}{"".join(self.layers)}{self._candles()}{"".join(self.top_layers)}</svg>')


def synth(rows, start="2026-01-05", freq="B") -> pd.DataFrame:
    """Build a DataFrame from (open, high, low, close) tuples for schematic diagrams."""
    idx = pd.date_range(start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


def path_to_bars(points, noise=0.25):
    """Turn a list of close prices into plausible candles (for schematics)."""
    rows, prev = [], points[0]
    for k, p in enumerate(points):
        o = prev
        wig = noise * (1 + (k % 3) * 0.3)
        rows.append((o, max(o, p) + wig, min(o, p) - wig, p))
        prev = p
    return rows
