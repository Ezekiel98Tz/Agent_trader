from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from agent_trader.strategy.fvg import detect_fvgs_m15
from agent_trader.types import Side


def test_detects_bullish_fvg():
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    df = pd.DataFrame(
        [
            {"time": t0, "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005, "volume": 1},
            {"time": t0, "open": 1.1005, "high": 1.1020, "low": 1.1000, "close": 1.1018, "volume": 1},
            {"time": t0, "open": 1.1025, "high": 1.1030, "low": 1.1021, "close": 1.1028, "volume": 1},
        ]
    )
    fvgs = detect_fvgs_m15(df, min_gap=0.0)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction == Side.BUY
    assert abs(f.bottom - 1.1010) < 1e-9
    assert abs(f.top - 1.1021) < 1e-9


def test_detects_bearish_fvg():
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    df = pd.DataFrame(
        [
            {"time": t0, "open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1005, "volume": 1},
            {"time": t0, "open": 1.1005, "high": 1.1008, "low": 1.0985, "close": 1.0988, "volume": 1},
            {"time": t0, "open": 1.0980, "high": 1.0987, "low": 1.0975, "close": 1.0982, "volume": 1},
        ]
    )
    fvgs = detect_fvgs_m15(df, min_gap=0.0)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction == Side.SELL
    assert abs(f.top - 1.0995) < 1e-9
    assert abs(f.bottom - 1.0987) < 1e-9

