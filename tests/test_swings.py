"""Module 1 tests: known-answer fixtures + no-lookahead check."""
import copy

import pandas as pd
import pytest

from ict_engine.data.loader import load_csv
from ict_engine.detectors.swings import detect_swings, swing_table, swings_as_of
from tests.conftest import make_ohlc

#            0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17
HIGHS = [1, 3, 2, 5, 2, 4, 1, 8, 2, 4, 1, 3, 0, 6, 1, 5, 1, 2]


def highs_only(tab):
    return tab[tab.side == "high"].set_index("bar")


def test_short_term_highs(cfg):
    tab = highs_only(swing_table(make_ohlc(HIGHS), cfg))
    assert list(tab.index) == [1, 3, 5, 7, 9, 11, 13, 15]


def test_intermediate_and_long_term_levels(cfg):
    tab = highs_only(swing_table(make_ohlc(HIGHS), cfg))
    assert tab.loc[3, "type"] == "ITH"
    assert tab.loc[13, "type"] == "ITH"
    assert tab.loc[7, "type"] == "LTH"
    assert tab.loc[9, "type"] == "STH"


def test_confirmation_bars(cfg):
    df = make_ohlc(HIGHS)
    ev = detect_swings(df, cfg)
    lth = ev[(ev.bar == 7) & (ev.side == "high")].set_index("level")["confirm_bar"]
    assert lth.to_dict() == {1: 8, 2: 10, 3: 16}


def test_broken_and_unbroken(cfg):
    tab = highs_only(swing_table(make_ohlc(HIGHS), cfg))
    assert tab.loc[3, "broken_date"] == make_ohlc(HIGHS).index[7]
    assert tab.loc[7, "unbroken"]
    assert tab.loc[13, "unbroken"]
    assert not tab.loc[1, "unbroken"]


def test_lows_mirror_highs(cfg):
    neg = [-h for h in HIGHS]
    df = make_ohlc(highs=[x + 1 for x in neg], lows=neg)
    lows = swing_table(df, cfg)
    lows = lows[lows.side == "low"].set_index("bar")
    assert list(lows.index) == [1, 3, 5, 7, 9, 11, 13, 15]
    assert lows.loc[7, "type"] == "LTL"


def test_non_strict_allows_equal_neighbours(cfg):
    c = copy.deepcopy(cfg)
    df = make_ohlc([1, 3, 3, 1])
    assert highs_only(swing_table(df, c)).empty
    c["swings"]["strict"] = False
    assert set(highs_only(swing_table(df, c)).index) == {1, 2}


def test_close_break_mode(cfg):
    c = copy.deepcopy(cfg)
    c["swings"]["break_on"] = "close"
    # bar 7 wick (8) trades above the 5 at bar 3 but its close (7.5) also does -> still broken
    tab = highs_only(swing_table(make_ohlc(HIGHS), c))
    assert tab.loc[3, "broken_date"] == make_ohlc(HIGHS).index[7]


def _check_no_lookahead(df, cfg, cols=("date", "side", "price", "type", "unbroken")):
    full = swing_table(df, cfg)
    for n in range(5, len(df) + 1):
        prefix = swing_table(df.iloc[:n], cfg)
        known = swings_as_of(full, df.index[n - 1])
        if prefix.empty:
            assert known.empty
            continue
        a = prefix[list(cols)].sort_values(["date", "side"]).reset_index(drop=True)
        b = known[list(cols)].sort_values(["date", "side"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_no_lookahead_synthetic(cfg):
    _check_no_lookahead(make_ohlc(HIGHS), cfg)


def test_no_lookahead_nifty(cfg):
    try:
        df = load_csv("NIFTY")
    except FileNotFoundError:
        pytest.skip("NIFTY.csv not present")
    _check_no_lookahead(df.iloc[-150:], cfg)
