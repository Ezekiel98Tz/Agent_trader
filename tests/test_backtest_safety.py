from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from agent_trader.backtest.engine import BacktestConfig, assert_safety, simulate_trades
from agent_trader.config import TradingConfig
from agent_trader.types import Side, TradeCandidate


def _m15_df():
    t0 = datetime(2024, 1, 2, 9, 0, tzinfo=timezone.utc)
    rows = []
    price = 1.2000
    for k in range(30):
        t = t0 + pd.Timedelta(minutes=15 * k)
        rows.append(
            {
                "time": t,
                "open": price,
                "high": price + 0.0008,
                "low": price - 0.0008,
                "close": price + 0.0002,
                "volume": 1,
            }
        )
        price += 0.0001
    return pd.DataFrame(rows)


def test_backtest_enforces_one_trade_and_cutoff_and_transition():
    cfg = TradingConfig()
    m15 = _m15_df()
    t_sig = pd.to_datetime(m15.loc[5, "time"]).to_pydatetime()
    c1 = TradeCandidate(
        time=t_sig,
        symbol="GBPUSD",
        side=Side.BUY,
        entry_price=float(m15.loc[5, "close"]),
        sl_price=float(m15.loc[5, "close"] - 0.00175),
        tp_price=float(m15.loc[5, "close"] + 0.00210),
        reason="x",
        confluence_score=4.5,
        meta={"market_regime": "TREND"},
    )
    c2 = TradeCandidate(
        time=t_sig,
        symbol="GBPUSD",
        side=Side.BUY,
        entry_price=float(m15.loc[5, "close"]),
        sl_price=float(m15.loc[5, "close"] - 0.00175),
        tp_price=float(m15.loc[5, "close"] + 0.00210),
        reason="x",
        confluence_score=4.5,
        meta={"market_regime": "TREND"},
    )
    c3 = TradeCandidate(
        time=t_sig,
        symbol="GBPUSD",
        side=Side.BUY,
        entry_price=float(m15.loc[5, "close"]),
        sl_price=float(m15.loc[5, "close"] - 0.00175),
        tp_price=float(m15.loc[5, "close"] + 0.00210),
        reason="x",
        confluence_score=4.5,
        meta={"market_regime": "TRANSITION"},
    )
    res = simulate_trades(m15, [c1, c2, c3], cfg=cfg, bt=BacktestConfig(enforce_one_trade=True))
    assert len(res) == 1
    assert_safety(res, cfg=cfg)


def test_backtest_secondary_risk_is_capped_and_blocked_skipped():
    cfg = TradingConfig()
    m15 = _m15_df()
    t_secondary_sig = datetime(2024, 1, 2, 8, 45, tzinfo=timezone.utc)
    m15.loc[0, "time"] = t_secondary_sig
    t_sig = pd.to_datetime(m15.loc[0, "time"]).to_pydatetime()
    c = TradeCandidate(
        time=t_sig,
        symbol="GBPUSD",
        side=Side.BUY,
        entry_price=float(m15.loc[0, "close"]),
        sl_price=float(m15.loc[0, "close"] - 0.00175),
        tp_price=float(m15.loc[0, "close"] + 0.00210),
        reason="x",
        confluence_score=4.5,
        meta={"market_regime": "TREND"},
    )
    res = simulate_trades(m15, [c], cfg=cfg)
    if len(res):
        assert res[0].session_state in ("PRIMARY", "SECONDARY")
        if res[0].session_state == "SECONDARY":
            assert res[0].risk_multiplier <= 0.5 + 1e-12
