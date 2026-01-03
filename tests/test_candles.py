from __future__ import annotations

import pandas as pd

from agent_trader.strategy.candles import is_bearish_engulfing, is_bullish_engulfing, is_pinbar


def test_bullish_engulfing():
    prev = pd.Series({"open": 1.0, "high": 1.01, "low": 0.99, "close": 0.995})
    cur = pd.Series({"open": 0.994, "high": 1.02, "low": 0.993, "close": 1.015})
    assert is_bullish_engulfing(prev, cur)


def test_bearish_engulfing():
    prev = pd.Series({"open": 1.0, "high": 1.02, "low": 0.99, "close": 1.015})
    cur = pd.Series({"open": 1.016, "high": 1.018, "low": 0.98, "close": 0.992})
    assert is_bearish_engulfing(prev, cur)


def test_pinbar_bull():
    row = pd.Series({"open": 1.0, "high": 1.005, "low": 0.98, "close": 1.002})
    ok, side = is_pinbar(row, min_wick_ratio=2.0)
    assert ok
    assert side == "bull"

