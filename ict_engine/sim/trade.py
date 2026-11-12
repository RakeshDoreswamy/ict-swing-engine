"""One set of trade-management rules, shared by the walk-forward and the Time Machine.

    manage(o, h, l, c, day, start_i, entry, stop, t1, t2, valid_sessions, hold_bars, partial)

Arrays are plain numpy (one bar per element); ``day`` numbers the sessions (0, 0, …, 1, 1, …).
Rules, in order:
  fill   : a resting buy limit at ``entry`` fills on the first bar whose low ≤ entry, at the open if
           the bar opens below it; the order lives for ``valid_sessions`` sessions from ``start_i``
  manage : on every bar from the fill bar on
             1. a gap: bar opens at or below the current stop → exit at the open
             2. low ≤ current stop → exit at the stop (checked before targets: conservative)
             3. high ≥ T1 → take ``partial`` off at T1, move the stop to the fill price
             4. after T1, high ≥ T2 → exit the rest at T2
  time   : exit at the close ``hold_bars`` bars after the fill
Returns (result, fill_i, exit_i, fill_px, R_gross); R is per unit of initial risk (fill − stop).
"""
from __future__ import annotations

import numpy as np


def manage(o, h, l, c, day, start_i, entry, stop, t1, t2, valid_sessions, hold_bars, partial):
    n = len(c)
    if start_i >= n:
        return "no data after scan", -1, -1, np.nan, np.nan
    last_day = day[start_i] + valid_sessions - 1
    fill_i = -1
    for i in range(start_i, n):
        if day[i] > last_day:
            break
        if l[i] <= entry:
            fill_i = i
            break
    if fill_i < 0:
        return "no fill", -1, -1, np.nan, np.nan
    fill = min(o[fill_i], entry)
    risk = fill - stop
    if risk <= 0:
        return "gap below stop at fill", fill_i, fill_i, fill, -1.0
    cur, half, real, size = stop, False, 0.0, 1.0
    has_t2 = t2 == t2 and t2 > t1
    end = min(n, fill_i + hold_bars)
    for i in range(fill_i, end):
        if i > fill_i and o[i] <= cur:
            real += size * (o[i] - fill) / risk
            return ("T1 then BE (gap)" if half else "stop (gap)"), fill_i, i, fill, real
        if l[i] <= cur:
            real += size * (cur - fill) / risk
            return ("T1 then breakeven" if half else "stop"), fill_i, i, fill, real
        if not half and h[i] >= t1:
            part = partial if has_t2 else 1.0
            real += part * (t1 - fill) / risk
            size -= part
            half, cur = True, fill
            if size <= 1e-9:
                return "T1", fill_i, i, fill, real
        if half and has_t2 and h[i] >= t2:
            real += size * (t2 - fill) / risk
            return "T1 + T2", fill_i, i, fill, real
    j = end - 1
    real += size * (c[j] - fill) / risk
    return ("open at end of data" if fill_i + hold_bars > n else "time stop"), fill_i, j, fill, real
