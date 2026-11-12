"""Time Machine tests: known-answer pools, determinism, pool building."""
import numpy as np
import pandas as pd
import pytest

from ict_engine.sim import timemachine as TM


def sessions(day_ratios, per=4, start="2026-01-05", p0=100.0):
    """Bars from a list of per-session bar ratios [(o,h,l,c) vs previous close] repeated per day."""
    rows, idx, prev = [], [], p0
    for d, day in zip(pd.bdate_range(start, periods=len(day_ratios)), day_ratios):
        for k, (ro, rh, rl, rc) in enumerate(day):
            o, h, l, c = prev * ro, prev * rh, prev * rl, prev * rc
            rows.append((o, h, l, c))
            idx.append(d + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=k))
            prev = c
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.DatetimeIndex(idx))


UP = [(1.0, 1.012, 0.999, 1.01)] * 4          # every bar +1 %, never dips more than 0.1 %
GAPDOWN = [(0.90, 0.905, 0.89, 0.90)] + [(1.0, 1.001, 0.999, 1.0)] * 3


def cfg(**kw):
    base = dict(replays=300, days=10, scale_vol=False, remove_drift=False, fan_paths=50)
    base.update(kw)
    return TM.TMConfig(**base)


def test_pool_shape_and_gaps():
    bars = sessions([UP] * 30)
    pool, info = TM.build_pool(bars)
    assert pool.shape == (29, 4, 4)                       # first session has no previous close
    assert info["sessions"] == 29 and info["bars_per_session"] == 4
    assert np.allclose(pool[:, :, 3], 1.01)


def test_short_sessions_are_left_out():
    bars = sessions([UP] * 30)
    bars = bars.drop(bars.index[10])                      # one bar missing on day 3
    pool, info = TM.build_pool(bars)
    assert info["sessions"] == 27                         # that day and the next (its previous close is wrong) dropped


def test_all_up_pool_always_reaches_targets():
    bars = sessions([UP] * 40)
    plan = TM.Plan("UP", entry=bars.close.iloc[-1] * 0.995, stop=bars.close.iloc[-1] * 0.95,
                   t1=bars.close.iloc[-1] * 1.03, t2=bars.close.iloc[-1] * 1.06)
    # the pool is all up-bars with 0.1 % dips: the limit 0.5 % below never fills
    o = TM.run(bars, plan, cfg())
    assert o["outcomes_pct"].get("no fill") == 100.0
    # a limit at the price fills at once and every replay goes to T1 + T2
    plan.entry = bars.close.iloc[-1] * 1.0005
    o = TM.run(bars, plan, cfg())
    assert o["outcomes_pct"] == {"T1 + T2": 100.0}
    assert o["verdict"].startswith("Strongly toward the target")


def test_gap_down_pool_stops_at_the_open():
    bars = sessions([GAPDOWN] * 40)
    last = bars.close.iloc[-1]
    plan = TM.Plan("GAP", entry=last * 0.999, stop=last * 0.95, t1=last * 1.05)
    o = TM.run(bars, plan, cfg())
    # day 1 gaps -10 % below the limit: fill at the open, below the stop → loss of at least 1R
    assert set(o["outcomes_pct"]) <= {"gap below stop at fill", "stop (gap)"}
    assert o["avg_R_filled"] <= -1.0


def test_same_seed_same_numbers():
    rng = np.random.default_rng(3)
    days = [[tuple(x) for x in np.c_[1 + rng.normal(0, 0.002, 4), 1.01 + rng.random(4) * 0.01,
                                       0.99 - rng.random(4) * 0.01, 1 + rng.normal(0, 0.006, 4)]] for _ in range(60)]
    bars = sessions(days)
    last = bars.close.iloc[-1]
    plan = TM.Plan("X", entry=last * 0.99, stop=last * 0.96, t1=last * 1.04, t2=last * 1.07)
    a, b = TM.run(bars, plan, cfg(seed=7)), TM.run(bars, plan, cfg(seed=7))
    assert a["outcomes_pct"] == b["outcomes_pct"] and a["avg_R_all"] == b["avg_R_all"]
    c = TM.run(bars, plan, cfg(seed=8))
    assert c["avg_R_all"] != a["avg_R_all"]


def test_vol_scaling_and_drift_removal():
    bars = sessions([UP] * 40)
    pool, _ = TM.build_pool(bars)
    p2, info = TM.adjust_pool(pool, bars, cfg(remove_drift=True, scale_vol=False))
    assert np.allclose(np.prod(p2[:, :, 3], axis=1), 1.0)   # no net drift left
    assert info["drift_removed_pct_per_day"] == pytest.approx((1.01 ** 4 - 1) * 100, rel=1e-6)


def test_needs_enough_sessions():
    with pytest.raises(ValueError, match="at least 20"):
        TM.run(sessions([UP] * 10), TM.Plan("X", 99, 95, 105), cfg())
