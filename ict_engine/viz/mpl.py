"""Matplotlib candlestick drawing with ICT annotation helpers (for high-resolution PNGs)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

C = {
    "up": "#1f9d6b", "dn": "#d1453b", "bull": "#1f9d6b", "bear": "#d1453b", "blue": "#2357c6",
    "purple": "#7a4cc2", "gold": "#b7791f", "grey": "#7a808a", "ink": "#1d1f23", "bg": "#ffffff",
    "hl": "#f3d9a4", "teal": "#0f8b8d",
}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": "#c9c6bf",
                     "axes.linewidth": 0.8, "axes.facecolor": "#ffffff", "figure.facecolor": "#ffffff"})


class Ax:
    """Wraps a matplotlib Axes; x is the bar position within ``df`` (no time gaps)."""

    def __init__(self, ax, df, title=None, date_fmt="%d %b %H:%M", nticks=8):
        self.ax, self.df, self.n = ax, df, len(df)
        self._rl = []  # y positions of right-edge labels, for collision avoidance
        self._candles()
        lo, hi = df.low.min(), df.high.max()
        pad = (hi - lo) * 0.08
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlim(-1, self.n + max(6, self.n * 0.16))
        step = max(1, -(-self.n // nticks))
        ax.set_xticks(range(0, self.n, step))
        ax.set_xticklabels([df.index[i].strftime(date_fmt) for i in range(0, self.n, step)], fontsize=7.5, color=C["grey"])
        ax.yaxis.tick_right()
        ax.tick_params(axis="y", labelsize=8, colors=C["grey"])
        ax.grid(axis="y", color="#eeebe5", lw=0.7)
        ax.set_axisbelow(True)
        if title:
            ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=C["ink"], pad=8)

    def _candles(self):
        w = 0.62
        for i, r in enumerate(self.df.itertuples()):
            col = C["up"] if r.close >= r.open else C["dn"]
            self.ax.vlines(i, r.low, r.high, color=col, lw=0.8, zorder=3)
            self.ax.add_patch(Rectangle((i - w / 2, min(r.open, r.close)), w, max(abs(r.close - r.open), 1e-9),
                                        color=col, zorder=3, lw=0))

    @property
    def right(self):
        return self.n - 0.5

    def zone(self, i0, i1, top, bot, color, label=None, alpha=0.16, where="left", fs=7.5, edge=True):
        i1 = self.right if i1 is None else i1 + 0.5
        self.ax.add_patch(Rectangle((i0 - 0.5, bot), i1 - (i0 - 0.5), top - bot, facecolor=color, alpha=alpha,
                                    edgecolor=color if edge else "none", lw=0.7, zorder=1))
        if label:
            x = i0 - 0.3 if where == "left" else i1 + 0.4
            self.ax.text(x, top, label, color=color, fontsize=fs, fontweight="bold", va="bottom",
                         ha="left", zorder=6, clip_on=True)

    def hline(self, price, i0=0, i1=None, color=C["grey"], label=None, ls="--", lw=1.0, fs=7.5):
        i1 = self.right if i1 is None else i1 + 0.5
        self.ax.hlines(price, i0 - 0.5, i1, colors=color, linestyles=ls, lw=lw, zorder=2)
        if label:
            y = self._free_y(price) if i1 >= self.right - 0.01 else price
            self.ax.text(i1 + 0.4, y, label, color=color, fontsize=fs, va="center", ha="left", fontweight="bold", zorder=6)

    def _free_y(self, y):
        lo, hi = self.ax.get_ylim()
        gap = (hi - lo) * 0.024
        for _ in range(40):
            clash = [v for v in self._rl if abs(v - y) < gap]
            if not clash:
                break
            y = min(clash) - gap if y <= min(clash) else max(clash) + gap
        self._rl.append(y)
        return y

    def rtext(self, y, text, color, fs=8.5):
        self.ax.text(self.right + 0.9, self._free_y(y), text, color=color, fontsize=fs, fontweight="bold", va="center")

    def mark(self, i, price, text, color, above=True, dy=0.035, fs=7.5, box=True, marker=None):
        rng = self.ax.get_ylim()[1] - self.ax.get_ylim()[0]
        y = price + rng * dy if above else price - rng * dy
        if marker:
            self.ax.scatter([i], [price], marker=marker, s=46, color=color, zorder=7, edgecolor="white", lw=0.6)
        bbox = dict(boxstyle="round,pad=0.25", fc="white", ec=color, lw=0.7, alpha=0.92) if box else None
        self.ax.annotate(text, (i, price), (i, y), color=color, fontsize=fs, ha="center",
                         va="bottom" if above else "top", fontweight="bold", zorder=8, bbox=bbox,
                         arrowprops=dict(arrowstyle="-", color=color, lw=0.7))

    def tri(self, i, price, color, up):
        self.ax.scatter([i], [price], marker="v" if not up else "^", s=16, color=color, zorder=6, lw=0)

    def shade(self, i, color=C["hl"], alpha=0.55):
        self.ax.axvspan(i - 0.5, i + 0.5, color=color, alpha=alpha, zorder=0, lw=0)

    def note(self, text, loc=(0.01, 0.97), fs=8.5):
        self.ax.text(*loc, text, transform=self.ax.transAxes, fontsize=fs, va="top", ha="left", color=C["ink"],
                     bbox=dict(boxstyle="round,pad=0.45", fc="#fbfaf7", ec="#d9d5cc", lw=0.8), zorder=9, wrap=True)

    def day_separators(self):
        days = self.df.index.normalize()
        for i in range(1, self.n):
            if days[i] != days[i - 1]:
                self.ax.axvline(i - 0.5, color="#d9d5cc", lw=0.6, ls=":", zorder=0)
