import numpy as np
import pandas as pd
import pytest

from ict_engine.config import load_config


@pytest.fixture
def cfg():
    return load_config()


def make_ohlc(highs, lows=None, start="2024-01-01"):
    """Synthetic daily OHLC from a list of highs (lows default to high - 1)."""
    highs = np.asarray(highs, dtype=float)
    lows = highs - 1 if lows is None else np.asarray(lows, dtype=float)
    mid = (highs + lows) / 2
    idx = pd.bdate_range(start, periods=len(highs), name="date")
    return pd.DataFrame(
        {"open": mid, "high": highs, "low": lows, "close": mid, "volume": 1000.0}, index=idx
    )
