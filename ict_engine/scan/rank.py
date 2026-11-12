"""Stage 4: grade and rank the 45m OTE candidates."""
from __future__ import annotations

import numpy as np
import pandas as pd


def grade(row: pd.Series, cfg: dict, market_ok: bool) -> str:
    c = cfg["scan"]["stage3"]
    rr_ok = row.get("rr_t2", np.nan) == row.get("rr_t2", np.nan) and row["rr_t2"] >= c["min_rr_t2"]
    conf_ok = bool(row.get("has_confluence")) or not c.get("require_confluence_for_a", True)
    if rr_ok and conf_ok and market_ok and row.get("bias") == "up":
        return "A"
    if rr_ok and (conf_ok or market_ok):
        return "B"
    return "C"


def score(df: pd.DataFrame, cfg: dict) -> pd.Series:
    w = cfg["scan"]["stage4"]["weights"]
    rr = df["rr_t2"].clip(upper=5).fillna(0) / 5
    conf = df["has_confluence"].astype(float)
    zone = (1 - df["zone_atr"].clip(upper=2).fillna(2) / 2)
    rs = df["rs_pct"].fillna(50) / 100
    dist = 1 - df["dist_to_entry_atr"].abs().clip(upper=3).fillna(3) / 3
    bias = (df["bias"] == "up").astype(float)
    s = (w["rr"] * rr + w["confluence"] * conf + w["zone"] * zone + w["rs"] * rs
         + w["distance"] * dist + w["bias"] * bias)
    return (s * 100).round(1)


def rank(df: pd.DataFrame, cfg: dict, market_ok: bool) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["grade"] = df.apply(lambda r: grade(r, cfg, market_ok), axis=1)
    df["score"] = score(df, cfg)
    df["qty_1pct"] = (cfg["risk"]["capital"] * cfg["risk"]["risk_per_trade_pct"] / 100
                      / (df["risk"] * cfg["risk"]["gap_slippage_factor"])).fillna(0).astype(int)
    order = {"A": 0, "B": 1, "C": 2}
    df["_g"] = df["grade"].map(order)
    return df.sort_values(["_g", "score"], ascending=[True, False]).drop(columns="_g")
