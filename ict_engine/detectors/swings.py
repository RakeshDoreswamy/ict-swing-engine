"""Module 1 - Institutional swing points (ICT Month 5, "Defining Institutional Swing Points").

Definitions (exact rules)
-------------------------
Short-term high (STH)
    Bar ``i`` whose high is strictly above the highs of the ``fractal_left`` bars before it
    and the ``fractal_right`` bars after it (default 1 and 1: the classic 3-bar fractal).
    It is *confirmed* at the close of bar ``i + fractal_right``; before that it does not exist.
Short-term low (STL)
    Mirror image using lows (strictly below its neighbours).
Intermediate-term high (ITH)
    An STH whose previous STH and next STH are both lower. Confirmed when that next STH is
    confirmed.
Long-term high (LTH)
    An ITH whose previous ITH and next ITH are both lower. Confirmed when that next ITH is
    confirmed.
ITL / LTL
    Mirror images on the low side.
Broken / unbroken
    A swing high is broken on the first later bar whose high (``break_on: wick``) or close
    (``break_on: close``) trades above it. Lows mirror this. An unbroken swing is part of
    the "open float" used in module 2.

No lookahead: every row carries ``confirm_date``. Use :func:`swings_as_of` to see only what
was knowable on a given date.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEVEL_NAMES = {
    "high": {1: "STH", 2: "ITH", 3: "LTH"},
    "low": {1: "STL", 2: "ITL", 3: "LTL"},
}
TABLE_COLS = [
    "bar", "date", "side", "price", "type", "level", "confirm_date",
    "ith_confirm_date", "lth_confirm_date", "broken_date", "unbroken",
]
EVENT_COLS = ["bar", "date", "side", "price", "level", "level_name", "confirm_bar", "confirm_date"]


def _beats(a: float, b: float, side: str, strict: bool) -> bool:
    """True if ``a`` is a more extreme price than ``b`` for this side."""
    if side == "high":
        return a > b if strict else a >= b
    return a < b if strict else a <= b


def _fractals(df: pd.DataFrame, side: str, left: int, right: int, strict: bool) -> list[dict]:
    px = df[side].to_numpy()
    out = []
    for i in range(left, len(px) - right):
        if all(_beats(px[i], px[j], side, strict) for j in range(i - left, i)) and all(
            _beats(px[i], px[j], side, strict) for j in range(i + 1, i + right + 1)
        ):
            out.append({"bar": i, "price": float(px[i]), "confirm_bar": i + right})
    return out


def _promote(seq: list[dict], side: str, strict: bool) -> list[dict]:
    """Next level up: members of ``seq`` more extreme than both sequence neighbours."""
    out = []
    for k in range(1, len(seq) - 1):
        prev_, cur, next_ = seq[k - 1], seq[k], seq[k + 1]
        if _beats(cur["price"], prev_["price"], side, strict) and _beats(
            cur["price"], next_["price"], side, strict
        ):
            out.append({**cur, "confirm_bar": max(cur["confirm_bar"], next_["confirm_bar"])})
    return out


def detect_swings(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Return one row per (swing, level) event, sorted by confirmation.

    An LTH therefore appears three times: as STH, ITH and LTH, each with its own
    ``confirm_date``. That keeps the history point-in-time correct.
    """
    s = cfg["swings"]
    rows = []
    dates = df.index
    for side in ("high", "low"):
        seq = _fractals(df, side, s["fractal_left"], s["fractal_right"], s["strict"])
        for level in (1, 2, 3):
            if level > 1:
                seq = _promote(seq, side, s["strict"])
            for e in seq:
                rows.append(
                    {
                        **e,
                        "date": dates[e["bar"]],
                        "side": side,
                        "level": level,
                        "level_name": LEVEL_NAMES[side][level],
                        "confirm_date": dates[e["confirm_bar"]],
                    }
                )
    ev = pd.DataFrame(rows, columns=EVENT_COLS)
    return ev.sort_values(["confirm_bar", "bar", "level"]).reset_index(drop=True)


def _break_bar(df: pd.DataFrame, bar: int, price: float, side: str, break_on: str) -> int | None:
    col = side if break_on == "wick" else "close"
    later = df[col].to_numpy()[bar + 1 :]
    hit = np.nonzero(later > price if side == "high" else later < price)[0]
    return int(bar + 1 + hit[0]) if hit.size else None


def swing_table(df: pd.DataFrame, cfg: dict, events: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per swing at its highest level, with break information (full-history view).

    Columns: date, price, side, type (STH/ITH/LTH/...), level, confirm_date,
    sth/ith/lth confirm dates, broken_date, unbroken.
    """
    ev = detect_swings(df, cfg) if events is None else events
    if ev.empty:
        return pd.DataFrame(columns=TABLE_COLS)
    wide = ev.pivot_table(index=["bar", "side"], columns="level", values="confirm_bar", aggfunc="first")
    rows = []
    for (bar, side), conf in wide.iterrows():
        top = int(conf.dropna().index.max())
        price = float(df[side].iloc[bar])
        brk = _break_bar(df, bar, price, side, cfg["swings"]["break_on"])
        rows.append(
            {
                "bar": bar,
                "date": df.index[bar],
                "side": side,
                "price": price,
                "type": LEVEL_NAMES[side][top],
                "level": top,
                "confirm_date": df.index[int(conf[1])],
                "ith_confirm_date": df.index[int(conf[2])] if 2 in conf and pd.notna(conf.get(2)) else pd.NaT,
                "lth_confirm_date": df.index[int(conf[3])] if 3 in conf and pd.notna(conf.get(3)) else pd.NaT,
                "broken_date": df.index[brk] if brk is not None else pd.NaT,
            }
        )
    tab = pd.DataFrame(rows).sort_values("bar").reset_index(drop=True)
    tab["unbroken"] = tab["broken_date"].isna()
    return tab


def swings_as_of(table: pd.DataFrame, as_of) -> pd.DataFrame:
    """Point-in-time view: swings confirmed by ``as_of``, their level and break status then."""
    as_of = pd.Timestamp(as_of)
    t = table[table["confirm_date"] <= as_of].copy()
    if t.empty:
        return t
    lvl = np.where(t["lth_confirm_date"] <= as_of, 3, np.where(t["ith_confirm_date"] <= as_of, 2, 1))
    t["level"] = lvl
    t["type"] = [LEVEL_NAMES[s][l] for s, l in zip(t["side"], lvl)]
    t.loc[t["broken_date"] > as_of, "broken_date"] = pd.NaT
    t["unbroken"] = t["broken_date"].isna()
    return t.reset_index(drop=True)
