"""Synthetic 45m paths with a known sweep → MSS → OTE structure."""
import pandas as pd


def zigzag(pivots, steps=3, start="2026-10-01 09:15", freq="45min"):
    """Candles walking linearly between pivots; each pivot candle pokes 0.5 beyond (a clean fractal)."""
    rows, prev = [], pivots[0]
    for k in range(1, len(pivots)):
        a, b = pivots[k - 1], pivots[k]
        for j in range(1, steps + 1):
            c = a + (b - a) * j / steps
            o = prev
            hi, lo = max(o, c) + 0.2, min(o, c) - 0.2
            if j == steps:
                if b > a:
                    hi = c + 0.5
                else:
                    lo = c - 0.5
            rows.append([o, hi, lo, c])
            prev = c
    return rows


def ote_path(pull=()):
    """Downtrend → sell-side sweep of the 105 low → bullish MSS → rally to ~118.5 → optional pullback.

    Leg low = 103.0 (sweep wick), leg high = 118.5. OTE 62% = 108.89, 70.5% = 107.57, 79% = 106.25.
    """
    rows = zigzag([132, 126, 129, 123, 126, 120, 123, 117, 120, 114, 117, 111, 114, 108, 111, 105, 108])
    rows.append([108.0, 108.2, 103.0, 106.0])      # sweep: wick below the 104.5 swing low, close above it
    rows.append([106.0, 106.6, 105.6, 106.4])
    rows.append([106.4, 111.5, 106.3, 111.3])      # MSS: closes above the 108.5 STH with displacement
    rows.append([111.3, 112.4, 110.9, 112.0])      # bullish FVG between 106.6 (c1 high) and 110.9 (c3 low)
    rows.append([112.0, 115.2, 111.8, 115.0])
    rows.append([115.0, 118.5, 114.8, 118.0])      # leg high 118.5
    c = 118.0
    for low in pull:
        rows.append([c, c + 0.1, low, (c + low) / 2])
        c = (c + low) / 2
    idx = pd.date_range("2026-10-01 09:15", periods=len(rows), freq="45min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)
