"""Known-answer tests for the first-pass detectors."""
import pandas as pd

from ict_engine.detectors.basic import displacement, fvgs, order_blocks, sweeps
from ict_engine.detectors.swings import swing_table


def bars(rows, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(rows), name="date")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


def test_bullish_fvg():
    df = bars([(10, 11, 9, 10.5), (10.5, 15, 10.4, 14.8), (14.8, 16, 12, 15.5), (15.5, 16, 14, 15)])
    g = fvgs(df)
    bull = g[g.side == "bull"].iloc[0]
    assert (bull.bar, bull.bottom, bull.top, bull.ce) == (1, 11, 12, 11.5)


def test_fvg_fill_and_inverse():
    df = bars([(10, 11, 9, 10.5), (10.5, 15, 10.4, 14.8), (14.8, 16, 12, 15.5), (15, 15, 10.5, 10.6)])
    bull = fvgs(df).query("side == 'bull'").iloc[0]
    assert bull.filled_bar == 3 and bull.inverse_bar == 3


def test_displacement_and_order_block():
    flat = [(10, 10.5, 9.5, 10.1)] * 15
    df = bars(flat + [(10.2, 10.3, 9.6, 9.8), (9.8, 14, 9.7, 13.9)])
    assert displacement(df).iloc[-1] == 1
    ob = order_blocks(df).query("side == 'bull'").iloc[-1]
    assert ob.bar == 15 and ob.bottom == 9.6 and ob.top == 10.3


def test_sell_side_sweep(cfg):
    #                 swing low at bar 2 (low 8)        bar 6 wicks to 7.5, closes 9
    df = bars([(10, 11, 9, 10), (10, 10.5, 8.8, 9), (9, 9.5, 8, 9.2), (9.2, 11, 9, 10.8),
               (10.8, 11.5, 10, 11), (11, 11.2, 9.5, 10), (10, 10.2, 7.5, 9), (9, 10, 8.5, 9.8)])
    sw = swing_table(df, cfg)
    s = sweeps(df, sw)
    assert len(s) and s.iloc[0].bar == 6 and s.iloc[0].side == "sell-side" and s.iloc[0].level == 8
