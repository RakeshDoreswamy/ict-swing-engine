"""Scanner tests: 45m resampling, bhavcopy parsing, stage 1, the OTE state machine, end to end."""
import copy

import numpy as np
import pandas as pd
import pytest

from ict_engine.data.providers.nse import parse_bhavcopy
from ict_engine.data.resample import resample_session
from ict_engine.scan.ote import find_ote_setup
from ict_engine.scan.stages import stage1_universe
from tests.scan_fixtures import ote_path


# ---------------------------------------------------------------- 45m resampling
def m15_days(n_days=2):
    idx = []
    for d in pd.bdate_range("2026-11-02", periods=n_days):
        idx += list(pd.date_range(d + pd.Timedelta("09:15:00"), d + pd.Timedelta("15:15:00"), freq="15min"))
    idx = pd.DatetimeIndex(idx)
    v = np.arange(len(idx), dtype=float)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1, "close": v + 0.5, "volume": 1.0}, index=idx)


def test_45m_merge_last_partial():
    m15 = m15_days()
    assert len(m15) == 50                      # 25 x 15m bars per day
    m45 = resample_session(m15, 45, "09:15", "15:30", True)
    day = m45[m45.index.normalize() == m45.index[0].normalize()]
    assert len(day) == 8
    assert list(day.index.strftime("%H:%M")) == ["09:15", "10:00", "10:45", "11:30", "12:15", "13:00", "13:45", "14:30"]
    assert day.volume.iloc[0] == 3 and day.volume.iloc[-1] == 4   # last candle = 14:30-15:30
    first = m15.iloc[:3]
    assert day.iloc[0].open == first.open.iloc[0] and day.iloc[0].close == first.close.iloc[-1]
    assert day.iloc[0].high == first.high.max() and day.iloc[0].low == first.low.min()


def test_45m_keep_partial_bar():
    m45 = resample_session(m15_days(), 45, "09:15", "15:30", False)
    day = m45[m45.index.normalize() == m45.index[0].normalize()]
    assert len(day) == 9 and day.index[-1].strftime("%H:%M") == "15:15" and day.volume.iloc[-1] == 1


def test_45m_never_spans_sessions():
    m45 = resample_session(m15_days(3), 45)
    assert (m45.groupby(m45.index.normalize()).size() == 8).all()


# ---------------------------------------------------------------- bhavcopy
UDIFF = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4
2026-11-12,2026-11-12,CM,NSE,STK,2885,INE002A01018,RELIANCE,EQ,,,,,RELIANCE INDUSTRIES LTD,1500.0,1520.5,1495.0,1510.2,1510.0,1498.0,,1510.2,,,1000000,1510200000.0,50000,F1,1,,,,,
2026-11-12,2026-11-12,CM,NSE,STK,999,INE000X01010,SOMEBOND,N1,,,,,BOND,100,101,99,100,100,100,,100,,,10,1000,1,F1,1,,,,,
"""
LEGACY = """SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,
TCS,EQ,3500,3550,3480,3540,3541,3490,200000,708000000,12-NOV-2026,9000,INE467B01029,
"""


def test_parse_bhavcopy_udiff():
    df = parse_bhavcopy(UDIFF)
    assert list(df.symbol) == ["RELIANCE"]                       # non-EQ/BE series dropped
    r = df.iloc[0]
    assert (r.open, r.high, r.low, r.close, r.volume) == (1500.0, 1520.5, 1495.0, 1510.2, 1000000)
    assert r.turnover == 1510200000.0 and r.date == pd.Timestamp("2026-11-12")


def test_parse_bhavcopy_legacy():
    r = parse_bhavcopy(LEGACY).iloc[0]
    assert r.symbol == "TCS" and r.close == 3540 and r.date == pd.Timestamp("2026-11-12")


# ---------------------------------------------------------------- stage 1
def panel(n=260):
    dates = pd.bdate_range("2025-11-03", periods=n)
    rows = []
    specs = {"GOOD": (500, 4e5, 0.02), "ILLIQ": (500, 1e3, 0.02), "PENNY": (20, 1e7, 0.02), "SLEEPY": (500, 4e5, 0.001)}
    for sym, (px, vol, rng) in specs.items():
        for k, d in enumerate(dates):
            c = px * (1 + 0.0005 * k)
            rows.append([d, sym, c, c * (1 + rng), c * (1 - rng), c, vol, c * vol])
    return pd.DataFrame(rows, columns=["date", "symbol", "open", "high", "low", "close", "volume", "turnover"])


def test_stage1_filters(cfg):
    s1 = stage1_universe(panel(), cfg, exclude=set())
    assert s1.loc["GOOD", "pass"]
    assert "turnover" in s1.loc["ILLIQ", "reason"]
    assert "price" in s1.loc["PENNY", "reason"]
    assert "ATR%" in s1.loc["SLEEPY", "reason"]
    s1x = stage1_universe(panel(), cfg, exclude={"GOOD"})
    assert "exclude" in s1x.loc["GOOD", "reason"]
    short = stage1_universe(panel(100), cfg)
    assert "history" in short.loc["GOOD", "reason"]


# ---------------------------------------------------------------- stage 3: OTE state machine
@pytest.mark.parametrize("pull,state", [
    ((117.2,), "waiting"),            # shallow pullback, above the 62% line
    ((113, 108.5), "in_zone"),        # reached 62% (108.89) but not 70.5% (107.57)
    ((112, 107.0), "triggered"),      # touched the 70.5% entry
    ((110, 102.5), "invalid"),        # took the 103.0 sweep low
])
def test_ote_states(cfg, pull, state):
    r = find_ote_setup(ote_path(pull), cfg, daily_bsl=[130.0])
    assert r["state"] == state
    assert (r["sweep_bar"], r["mss_bar"]) == (48, 50)
    assert r["leg_low"] == 103.0 and r["leg_high"] == 118.5
    assert r["ote_62"] == pytest.approx(118.5 - 0.62 * 15.5)
    assert r["entry"] == pytest.approx(118.5 - 0.705 * 15.5)
    assert r["ote_79"] == pytest.approx(118.5 - 0.79 * 15.5)
    assert r["stop"] < r["leg_low"] and r["entry"] - r["stop"] >= 0.5 * r["atr45"] - 1e-9
    assert {z[0] for z in r["confluence"]} == {"FVG", "OB"}
    assert r["t2"] == 130.0 and r["rr_t2"] > 2


def test_ote_needs_a_pullback(cfg):
    assert "no pullback" in find_ote_setup(ote_path(()), cfg)["reason"]


def test_ote_needs_t2(cfg):
    r = find_ote_setup(ote_path((117.2,)), cfg, daily_bsl=None)
    assert r["state"] == "waiting" and "no open buy-side liquidity" in r["reason"]


def test_ote_stale(cfg):
    c = copy.deepcopy(cfg)
    c["scan"]["stage3"]["stale_after_high"] = 2
    c["scan"]["stage3"]["max_setup_age"] = 60
    r = find_ote_setup(ote_path((117.5, 117.4, 117.3, 117.2)), c, daily_bsl=[130.0])
    assert r["state"] == "stale"


def test_ote_no_lookahead(cfg):
    """The setup seen on the bar the pullback reaches the zone must not change when later bars arrive."""
    full = ote_path((113, 108.5, 112, 116))
    early = find_ote_setup(full.iloc[:-2], cfg, daily_bsl=[130.0])
    assert early["state"] == "in_zone" and early["leg_high"] == 118.5


# ---------------------------------------------------------------- end to end (offline)
def test_runner_end_to_end(cfg, tmp_path):
    from ict_engine.data.store import Store
    from ict_engine.scan.runner import run_scan

    c = copy.deepcopy(cfg)
    c["scan"]["store_dir"] = str(tmp_path / "store")
    c["scan"]["universe_file"] = str(tmp_path / "EQUITY_L.csv")
    c["scan"]["exclude_file"] = str(tmp_path / "exclude.csv")
    c["filters"]["event_calendar"] = str(tmp_path / "events.csv")
    p = panel()
    pd.DataFrame({"SYMBOL": p.symbol.unique(), "NAME OF COMPANY": "x", "SERIES": "EQ"}).to_csv(c["scan"]["universe_file"], index=False)
    st = Store(c["scan"]["store_dir"])
    st.write_daily_panel(p)
    idx = p[p.symbol == "GOOD"].set_index("date")[["open", "high", "low", "close", "volume"]]
    st.merge_series("index", "nifty500", idx)
    res = run_scan(c, fetch_intraday=False, force=True, workers=1, out_dir=tmp_path / "out", log=lambda *a: None)
    assert (tmp_path / "out" / "index.html").exists() and (tmp_path / "out" / "funnel.csv").exists()
    assert res["steps"][0] == ("NSE universe", 4)
    assert res["steps"][1][1] == 1                       # only GOOD survives stage 1
