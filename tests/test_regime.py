from __future__ import annotations

from agent_trader.market_regime.regime import classify_regime


def test_regime_trend():
    r = classify_regime(ema50_slope=0.00005, ema_alignment=0.00020, atr_percentile=0.80)
    assert r == "TREND"


def test_regime_range():
    r = classify_regime(ema50_slope=0.000001, ema_alignment=0.000001, atr_percentile=0.10)
    assert r == "RANGE"


def test_regime_transition():
    r = classify_regime(ema50_slope=0.00002, ema_alignment=0.00002, atr_percentile=0.50)
    assert r == "TRANSITION"

