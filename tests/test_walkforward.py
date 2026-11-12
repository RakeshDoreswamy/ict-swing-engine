"""Walk-forward tests: trade simulator known answers, point-in-time stage 2, order selection."""
import numpy as np
import pandas as pd
import pytest

from ict_engine.backtest import walkforward as W
from ict_engine.scan.stages import stage2_symbol

SETUP = {"entry": 100.0, "stop": 95.0, "t1": 110.0, "t2": 120.0, "leg_low": 96.0}


def bars(rows, per_day=4, start="2026-10-05"):
    idx = []
    for d in pd.bdate_range(start, periods=len(rows) // per_day + 1):
        idx += list(pd.date_range(d + pd.Timedelta("09:15:00"), periods=per_day, freq="60min"))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx[:len(rows)])


SIM = W.SimCfg(order_valid_sessions=2, hold_days=3, partial_at_t1=0.5)


def test_fill_t1_then_t2():
    b = bars([(103, 104, 101, 102), (102, 102, 99.5, 101),   # fills at 100
              (101, 111, 101, 110), (110, 121, 109, 120)])   # T1 then T2
    r = W.simulate(b, 0, SETUP, SIM, 4)
    assert r["result"] == "T1 + T2" and r["fill"] == 100.0
    assert r["R_gross"] == pytest.approx(0.5 * 10 / 5 + 0.5 * 20 / 5)   # 1 + 2 = 3R


def test_full_stop():
    b = bars([(101, 101, 99, 99.5), (99.5, 99.8, 94, 94.5)])
    r = W.simulate(b, 0, SETUP, SIM, 4)
    assert r["result"] == "stop" and r["R_gross"] == pytest.approx(-1.0)


def test_t1_then_breakeven():
    b = bars([(101, 101, 99, 100), (100, 111, 100, 109), (109, 109, 99, 99.5)])
    r = W.simulate(b, 0, SETUP, SIM, 4)
    assert r["result"] == "T1 then breakeven" and r["R_gross"] == pytest.approx(1.0)


def test_gap_through_stop_exits_at_open():
    b = bars([(101, 101, 99, 100), (93, 94, 92, 93)])
    r = W.simulate(b, 0, SETUP, SIM, 4)
    assert r["result"] == "stop (gap)" and r["R_gross"] == pytest.approx((93 - 100) / 5)


def test_gap_below_entry_fills_at_open():
    b = bars([(98, 99, 97, 98.5), (98.5, 111, 98, 110)])
    r = W.simulate(b, 0, SETUP, SIM, 4)
    assert r["fill"] == 98.0
    assert r["R_gross"] > 1.0                       # better fill, same targets, smaller risk


def test_stop_wins_when_both_hit_in_one_bar():
    b = bars([(101, 112, 94, 100)])
    assert W.simulate(b, 0, SETUP, SIM, 4)["result"] == "stop"


def test_order_expires_after_valid_sessions():
    rows = [(103, 104, 101, 102)] * 8 + [(102, 102, 99, 100)]     # touches entry on day 3
    assert W.simulate(bars(rows), 0, SETUP, SIM, 4)["result"] == "no fill"


def test_time_stop():
    rows = [(101, 101, 99.5, 100)] + [(100, 102, 99, 101)] * 20
    r = W.simulate(bars(rows), 0, SETUP, SIM, 4)
    assert r["result"] == "time stop" and r["R_gross"] == pytest.approx((101 - 100) / 5)


def test_costs_are_positive_and_small(cfg):
    c = W.cost_pct(cfg)
    assert 0.2 < c < 0.4           # ~0.21% STT + stamp + fees + 0.1% slippage


def test_select_orders_skips_refills():
    occ = pd.DataFrame([
        {"symbol": "X", "scan_date": pd.Timestamp("2026-10-01"), "mss_time": pd.Timestamp("2026-09-30 10:00"), "result": "no fill"},
        {"symbol": "X", "scan_date": pd.Timestamp("2026-10-02"), "mss_time": pd.Timestamp("2026-09-30 10:00"), "result": "stop"},
        {"symbol": "X", "scan_date": pd.Timestamp("2026-10-03"), "mss_time": pd.Timestamp("2026-09-30 10:00"), "result": "stop"},
        {"symbol": "Y", "scan_date": pd.Timestamp("2026-10-01"), "mss_time": pd.Timestamp("2026-09-30 11:00"), "result": "T1"},
    ])
    allowed = {("X", pd.Timestamp("2026-10-01")), ("X", pd.Timestamp("2026-10-02")), ("X", pd.Timestamp("2026-10-03"))}
    sel = W.select_orders(occ, allowed)
    assert list(sel.scan_date.dt.day) == [1, 2]          # re-placed after expiry, not after the fill; Y not allowed


def test_stage2_point_in_time_matches_live(cfg):
    """stage2_series(as of D) must equal the live stage2_symbol run on data truncated at D."""
    from ict_engine.data.loader import load_csv
    d = load_csv("NIFTY").assign(turnover=0.0)
    dates = list(d.index[-60::10])
    pit = W.stage2_series("NIFTY", d, dates, cfg).set_index("date")
    for D in dates:
        live = stage2_symbol("NIFTY", d[d.index <= D], cfg)
        row = pit.loc[D]
        assert row.bias == live["bias"]
        assert bool(row.discount) == bool(live["discount"])
        for k in ("eq", "zone_atr", "room_atr"):
            a, b = float(row[k]), float(live[k])
            assert (np.isnan(a) and np.isnan(b)) or (np.isinf(a) and np.isinf(b)) or a == pytest.approx(b), (D, k, a, b)
