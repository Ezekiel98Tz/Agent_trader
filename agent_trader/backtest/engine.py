from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal

import numpy as np
import pandas as pd

from agent_trader.config import TradingConfig
from agent_trader.session.session_filter import get_session_state
from agent_trader.types import Side, TradeCandidate
from agent_trader.utils import pip_value, price_to_pips, within_day_cutoff


@dataclass(frozen=True)
class BacktestFill:
    time: object
    price: float


@dataclass(frozen=True)
class BacktestTradeResult:
    candidate: TradeCandidate
    entry_fill: BacktestFill
    exit_fill: BacktestFill
    outcome: Literal["win", "loss", "breakeven", "cutoff", "expired"]
    pnl_pips: float
    r_multiple: float
    r_multiple_scaled: float
    risk_multiplier: float
    session_state: str
    market_regime: str


@dataclass(frozen=True)
class BacktestConfig:
    spread_pips: float = 1.2
    max_hold_bars: int = 48
    fill_policy: Literal["sl_first", "tp_first", "ohlc_path"] = "ohlc_path"
    enforce_one_trade: bool = True
    enforce_session: bool = True
    enforce_cutoff: bool = True


@dataclass(frozen=True)
class BacktestSummary:
    trades: int
    win_rate: float
    expectancy_r: float
    max_drawdown_r: float
    sharpe_proxy: float
    by_regime: dict[str, dict[str, float]]
    by_session: dict[str, dict[str, float]]


def _ohlc_path_first_hit(
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    tp: float,
    sl: float,
    side: Side,
    policy: Literal["sl_first", "tp_first", "ohlc_path"],
) -> Literal["tp", "sl", "none", "both"]:
    if side == Side.BUY:
        hit_tp = high >= tp
        hit_sl = low <= sl
    else:
        hit_tp = low <= tp
        hit_sl = high >= sl

    if not hit_tp and not hit_sl:
        return "none"
    if hit_tp and not hit_sl:
        return "tp"
    if hit_sl and not hit_tp:
        return "sl"

    if policy == "sl_first":
        return "sl"
    if policy == "tp_first":
        return "tp"

    bullish = close >= open_
    if side == Side.BUY:
        return "sl" if bullish else "tp"
    return "tp" if bullish else "sl"


def simulate_trades(
    m15: pd.DataFrame,
    candidates: list[TradeCandidate],
    *,
    cfg: TradingConfig,
    bt: BacktestConfig = BacktestConfig(),
    cutoff: time | None = None,
) -> list[BacktestTradeResult]:
    m15 = m15.reset_index(drop=True)
    times = pd.to_datetime(m15["time"]).to_numpy()
    idx_by_time = {pd.to_datetime(t).to_pydatetime(): i for i, t in enumerate(times)}
    out: list[BacktestTradeResult] = []
    spread = bt.spread_pips * pip_value(cfg.symbol)
    half = spread / 2.0
    cutoff_t = cutoff or cfg.day_end_cutoff

    in_position_until_idx = -1
    for c in sorted(candidates, key=lambda x: x.time):
        i = idx_by_time.get(c.time)
        if i is None:
            continue
        if bt.enforce_one_trade and i <= in_position_until_idx:
            continue
        if str(c.meta.get("market_regime", "")) == "TRANSITION":
            continue
        entry_idx = i + 1
        if entry_idx >= len(m15):
            continue
        entry_time = pd.to_datetime(times[entry_idx]).to_pydatetime()
        if bt.enforce_cutoff and not within_day_cutoff(entry_time, cfg.timezone, cutoff_t):
            continue
        if bt.enforce_session:
            ss = get_session_state(entry_time)
            if ss == "BLOCKED":
                continue
        else:
            ss = get_session_state(entry_time)

        risk_mult = 1.0 if ss == "PRIMARY" else (0.5 if ss == "SECONDARY" else 0.0)
        if risk_mult <= 0.0:
            continue

        sl_pips = price_to_pips(cfg.symbol, abs(c.entry_price - c.sl_price))
        tp_pips = price_to_pips(cfg.symbol, abs(c.tp_price - c.entry_price))
        if sl_pips <= 0 or tp_pips <= 0:
            continue

        mid_open = float(m15.loc[entry_idx, "open"])
        entry = mid_open + half if c.side == Side.BUY else mid_open - half
        sl = entry - (sl_pips * pip_value(cfg.symbol)) if c.side == Side.BUY else entry + (sl_pips * pip_value(cfg.symbol))
        tp = entry + (tp_pips * pip_value(cfg.symbol)) if c.side == Side.BUY else entry - (tp_pips * pip_value(cfg.symbol))

        exit_price = float(m15.loc[entry_idx, "close"])
        exit_time = entry_time
        outcome: Literal["win", "loss", "breakeven", "cutoff", "expired"] = "expired"

        for j in range(entry_idx, min(len(m15), entry_idx + bt.max_hold_bars)):
            bar_time = pd.to_datetime(times[j]).to_pydatetime()
            if bt.enforce_cutoff and not within_day_cutoff(bar_time, cfg.timezone, cutoff_t):
                mid = float(m15.loc[j, "open"])
                exit_price = (mid - half) if c.side == Side.BUY else (mid + half)
                exit_time = bar_time
                outcome = "cutoff"
                break

            o = float(m15.loc[j, "open"])
            h = float(m15.loc[j, "high"])
            l = float(m15.loc[j, "low"])
            cl = float(m15.loc[j, "close"])
            if c.side == Side.BUY:
                open_q = o - half
                high_q = h - half
                low_q = l - half
                close_q = cl - half
            else:
                open_q = o + half
                high_q = h + half
                low_q = l + half
                close_q = cl + half

            hit = _ohlc_path_first_hit(
                open_=open_q,
                high=high_q,
                low=low_q,
                close=close_q,
                tp=tp,
                sl=sl,
                side=c.side,
                policy=bt.fill_policy,
            )
            if hit == "tp":
                exit_price = tp
                exit_time = bar_time
                outcome = "win"
                break
            if hit == "sl":
                exit_price = sl
                exit_time = bar_time
                outcome = "loss"
                break

        pnl_pips = price_to_pips(cfg.symbol, (exit_price - entry) if c.side == Side.BUY else (entry - exit_price))
        r_mult = pnl_pips / sl_pips if sl_pips else 0.0
        if abs(pnl_pips) < 1e-6:
            outcome = "breakeven"
            r_mult = 0.0
        r_scaled = float(r_mult) * float(risk_mult)

        res = BacktestTradeResult(
            candidate=c,
            entry_fill=BacktestFill(time=entry_time, price=entry),
            exit_fill=BacktestFill(time=exit_time, price=exit_price),
            outcome=outcome,
            pnl_pips=float(pnl_pips),
            r_multiple=float(r_mult),
            r_multiple_scaled=float(r_scaled),
            risk_multiplier=float(risk_mult),
            session_state=str(ss),
            market_regime=str(c.meta.get("market_regime") or "UNKNOWN"),
        )
        out.append(res)
        if bt.enforce_one_trade:
            in_position_until_idx = idx_by_time.get(exit_time, j)
    return out


def summarize(results: list[BacktestTradeResult]) -> BacktestSummary:
    if not results:
        return BacktestSummary(
            trades=0,
            win_rate=0.0,
            expectancy_r=0.0,
            max_drawdown_r=0.0,
            sharpe_proxy=0.0,
            by_regime={},
            by_session={},
        )
    r = np.array([t.r_multiple_scaled for t in results], dtype=float)
    wins = sum(1 for t in results if t.outcome == "win")
    losses = sum(1 for t in results if t.outcome == "loss")
    denom = wins + losses if (wins + losses) else len(results)
    win_rate = wins / denom if denom else 0.0
    expectancy = float(np.mean(r)) if len(r) else 0.0
    eq = np.cumsum(r)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = float(np.max(dd)) if len(dd) else 0.0
    sharpe = 0.0
    if len(r) >= 5 and float(np.std(r, ddof=1)) > 1e-12:
        sharpe = float(np.mean(r) / np.std(r, ddof=1) * np.sqrt(len(r)))

    by: dict[str, list[float]] = {}
    by_wr: dict[str, tuple[int, int]] = {}
    for t in results:
        by.setdefault(t.market_regime, []).append(t.r_multiple_scaled)
        w, l = by_wr.get(t.market_regime, (0, 0))
        if t.outcome == "win":
            w += 1
        if t.outcome == "loss":
            l += 1
        by_wr[t.market_regime] = (w, l)

    by_regime: dict[str, dict[str, float]] = {}
    for k, arr in by.items():
        a = np.array(arr, dtype=float)
        w, l = by_wr.get(k, (0, 0))
        d = w + l if (w + l) else len(a)
        by_regime[k] = {
            "trades": float(len(a)),
            "win_rate": float(w / d) if d else 0.0,
            "expectancy_r": float(np.mean(a)) if len(a) else 0.0,
        }

    by_s: dict[str, list[float]] = {}
    by_s_wr: dict[str, tuple[int, int]] = {}
    for t in results:
        by_s.setdefault(t.session_state, []).append(t.r_multiple_scaled)
        w, l = by_s_wr.get(t.session_state, (0, 0))
        if t.outcome == "win":
            w += 1
        if t.outcome == "loss":
            l += 1
        by_s_wr[t.session_state] = (w, l)

    by_session: dict[str, dict[str, float]] = {}
    for k, arr in by_s.items():
        a = np.array(arr, dtype=float)
        w, l = by_s_wr.get(k, (0, 0))
        d = w + l if (w + l) else len(a)
        by_session[k] = {
            "trades": float(len(a)),
            "win_rate": float(w / d) if d else 0.0,
            "expectancy_r": float(np.mean(a)) if len(a) else 0.0,
        }

    return BacktestSummary(
        trades=len(results),
        win_rate=float(win_rate),
        expectancy_r=float(expectancy),
        max_drawdown_r=float(max_dd),
        sharpe_proxy=float(sharpe),
        by_regime=by_regime,
        by_session=by_session,
    )


def assert_safety(
    results: list[BacktestTradeResult],
    *,
    cfg: TradingConfig,
) -> None:
    last_exit: datetime | None = None
    for t in results:
        if str(t.candidate.meta.get("market_regime")) == "TRANSITION":
            raise AssertionError("trade during TRANSITION")
        if not within_day_cutoff(t.entry_fill.time, cfg.timezone, cfg.day_end_cutoff):
            raise AssertionError("trade after cutoff")
        if t.session_state == "BLOCKED":
            raise AssertionError("trade during BLOCKED")
        if t.session_state == "SECONDARY" and t.risk_multiplier > 0.5 + 1e-12:
            raise AssertionError("secondary risk cap violated")
        if last_exit is not None and pd.to_datetime(t.entry_fill.time) < pd.to_datetime(last_exit):
            raise AssertionError("more than one open position")
        last_exit = pd.to_datetime(t.exit_fill.time).to_pydatetime()
