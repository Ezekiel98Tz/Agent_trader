from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from agent_trader.config import TradingConfig
from agent_trader.indicators.atr import atr, rolling_percentile
from agent_trader.market_regime.regime import classify_regime
from agent_trader.session.session_filter import get_session_state
from agent_trader.strategy.candles import candle_stats, is_bearish_engulfing, is_bullish_engulfing, is_pinbar
from agent_trader.strategy.fvg import detect_fvgs_m15, latest_relevant_fvg
from agent_trader.strategy.support_resistance import compute_sr_context, distance_to_nearest, nearest_level
from agent_trader.strategy.trend import compute_trend_context
from agent_trader.types import Side, TradeCandidate
from agent_trader.utils import infer_session, pips_to_price, price_to_pips, within_day_cutoff


@dataclass(frozen=True)
class CandidateInputs:
    h4: pd.DataFrame
    h1: pd.DataFrame
    m15: pd.DataFrame


def generate_candidates(data: CandidateInputs, *, cfg: TradingConfig, live_gate: bool = False) -> list[TradeCandidate]:
    m15 = data.m15.reset_index(drop=True)
    m15_times = pd.to_datetime(m15["time"]).to_numpy()
    if live_gate and len(m15_times):
        latest_t = pd.to_datetime(m15_times[-1]).to_pydatetime()
        if get_session_state(latest_t) == "BLOCKED":
            return []

    h4_ctx = compute_trend_context(data.h4)
    h1_ctx = compute_trend_context(data.h1)
    atr14 = atr(m15, 14)
    atr_pct = rolling_percentile(atr14, window=250)
    fvgs = detect_fvgs_m15(m15, min_gap=0.0)

    h4_times = pd.to_datetime(data.h4["time"]).to_numpy()
    h1_times = pd.to_datetime(data.h1["time"]).to_numpy()

    last_sr_h1_idx = -1
    sr = compute_sr_context(data.h1, end_time=None)

    out: list[TradeCandidate] = []
    for i in range(210, len(m15)):
        t = pd.to_datetime(m15_times[i]).to_pydatetime()
        session_state = get_session_state(t)
        if session_state == "BLOCKED":
            continue
        if not within_day_cutoff(t, cfg.timezone, cfg.day_end_cutoff):
            continue
        session, overlap = infer_session(t, cfg.timezone)
        if session == "OffHours":
            continue

        close = float(m15.loc[i, "close"])
        t64 = pd.to_datetime(t).to_datetime64()
        h4_idx = int(h4_times.searchsorted(t64, side="right") - 1)
        h1_idx = int(h1_times.searchsorted(t64, side="right") - 1)
        if h4_idx < 0 or h1_idx < 0:
            continue

        h4_dir = str(h4_ctx.direction.iloc[h4_idx])
        h1_dir = str(h1_ctx.direction.iloc[h1_idx])
        atr_p = None if pd.isna(atr_pct.iloc[i]) else float(atr_pct.iloc[i])
        ema_slope = float(h1_ctx.ema50_slope.iloc[h1_idx])
        ema_align = float(h1_ctx.ema_alignment.iloc[h1_idx])
        regime = classify_regime(ema50_slope=ema_slope, ema_alignment=ema_align, atr_percentile=atr_p)
        if regime == "TRANSITION":
            continue

        if h1_idx != last_sr_h1_idx:
            last_sr_h1_idx = h1_idx
            sr = compute_sr_context(data.h1, end_time=pd.to_datetime(h1_times[h1_idx]).to_pydatetime())

        prev = m15.loc[i - 1]
        cur = m15.loc[i]
        pin_ok, pin_side = is_pinbar(cur, min_wick_ratio=2.0)
        cstats = candle_stats(cur)

        n_sup = nearest_level(close, sr.supports, kind="support")
        n_res = nearest_level(close, sr.resistances, kind="resistance")
        d_sup = None if n_sup is None else n_sup[1]
        d_res = None if n_res is None else n_res[1]
        a14 = float(atr14.iloc[i]) if pd.notna(atr14.iloc[i]) else None

        if regime == "TREND":
            if h4_dir != h1_dir or h1_dir == "range":
                continue
            side = Side.BUY if h1_dir == "up" else Side.SELL
            engulf = is_bullish_engulfing(prev, cur) if side == Side.BUY else is_bearish_engulfing(prev, cur)
            candle_ok = engulf or (pin_ok and ((pin_side == "bull" and side == Side.BUY) or (pin_side == "bear" and side == Side.SELL)))
            if not candle_ok:
                continue
            fvg_match = latest_relevant_fvg(m15, fvgs, idx=i, side=side, max_age_bars=96)
            if fvg_match is None:
                continue
            if a14 is None:
                continue
            if side == Side.BUY and (d_sup is None or d_sup > (a14 * 1.5)):
                continue
            if side == Side.SELL and (d_res is None or d_res > (a14 * 1.5)):
                continue
            sl = close - pips_to_price(cfg.symbol, cfg.risk_sl_pips) if side == Side.BUY else close + pips_to_price(cfg.symbol, cfg.risk_sl_pips)
            if side == Side.BUY:
                tp_anchor = close + (d_res if d_res is not None else (a14 * 2.0))
            else:
                tp_anchor = close - (d_sup if d_sup is not None else (a14 * 2.0))
            tp = float(tp_anchor)
            rr = abs(tp - close) / abs(close - sl) if abs(close - sl) > 0 else 0.0
            if rr < cfg.min_rr:
                continue
            confluence = 0.0
            confluence += 1.0
            confluence += 1.0 if fvg_match.inside else 0.5
            confluence += 0.5 if overlap else 0.0
            confluence += 0.5 if engulf else 0.0
            confluence += 0.25 if cstats.body > a14 * 0.25 else 0.0
            confluence += 0.25 if atr_p is not None and atr_p >= 0.6 else 0.0
            reason = "trend+sr+fvg+candle"
            setup_type = "trend_follow"
            fvg_size = price_to_pips(cfg.symbol, fvg_match.fvg.size)
            time_since_fvg = fvg_match.age_bars
            fvg_inside = fvg_match.inside
        else:
            if a14 is None:
                continue
            near_support = d_sup is not None and d_sup <= (a14 * 1.0)
            near_res = d_res is not None and d_res <= (a14 * 1.0)
            if not (near_support or near_res):
                continue
            if near_support and (not near_res or (d_sup is not None and d_res is not None and d_sup <= d_res)):
                side = Side.BUY
            else:
                side = Side.SELL
            engulf = is_bullish_engulfing(prev, cur) if side == Side.BUY else is_bearish_engulfing(prev, cur)
            candle_ok = engulf or (pin_ok and ((pin_side == "bull" and side == Side.BUY) or (pin_side == "bear" and side == Side.SELL)))
            if not candle_ok:
                continue
            fvg_match = latest_relevant_fvg(m15, fvgs, idx=i, side=side, max_age_bars=96)
            sl = close - pips_to_price(cfg.symbol, cfg.risk_sl_pips) if side == Side.BUY else close + pips_to_price(cfg.symbol, cfg.risk_sl_pips)
            if side == Side.BUY:
                tp_anchor = (n_res[0].price if n_res is not None else (close + a14 * 2.0))
            else:
                tp_anchor = (n_sup[0].price if n_sup is not None else (close - a14 * 2.0))
            tp = float(tp_anchor)
            rr = abs(tp - close) / abs(close - sl) if abs(close - sl) > 0 else 0.0
            if rr < cfg.min_rr:
                continue
            confluence = 0.0
            confluence += 1.0
            confluence += 0.75 if ((n_sup is not None and side == Side.BUY and n_sup[0].touched >= 2) or (n_res is not None and side == Side.SELL and n_res[0].touched >= 2)) else 0.25
            confluence += 0.5 if overlap else 0.0
            confluence += 0.5 if engulf else 0.0
            confluence += 0.25 if cstats.body > a14 * 0.25 else 0.0
            confluence += 0.25 if atr_p is not None and atr_p <= 0.4 else 0.0
            confluence += 0.25 if (fvg_match is not None and fvg_match.inside) else 0.0
            reason = "range+sr+candle"
            setup_type = "mean_reversion"
            fvg_size = None if fvg_match is None else price_to_pips(cfg.symbol, fvg_match.fvg.size)
            time_since_fvg = None if fvg_match is None else fvg_match.age_bars
            fvg_inside = None if fvg_match is None else fvg_match.inside

        out.append(
            TradeCandidate(
                time=t,
                symbol=cfg.symbol,
                side=side,
                entry_price=close,
                sl_price=float(sl),
                tp_price=float(tp),
                reason=reason,
                confluence_score=float(confluence),
                meta={
                    "session": session,
                    "session_overlap": bool(overlap),
                    "session_state": session_state,
                    "h4_trend": h4_dir,
                    "h1_trend": h1_dir,
                    "market_regime": regime,
                    "setup_type": setup_type,
                    "distance_to_support_pips": None if d_sup is None else price_to_pips(cfg.symbol, d_sup),
                    "distance_to_resistance_pips": None if d_res is None else price_to_pips(cfg.symbol, d_res),
                    "support_touch_count": None if n_sup is None else int(n_sup[0].touched),
                    "resistance_touch_count": None if n_res is None else int(n_res[0].touched),
                    "fvg_size": fvg_size,
                    "fvg_inside": fvg_inside,
                    "time_since_fvg_bars": time_since_fvg,
                    "atr14_pips": price_to_pips(cfg.symbol, float(atr14.iloc[i])) if pd.notna(atr14.iloc[i]) else None,
                    "atr_percentile": atr_p,
                    "rr_ratio": float(rr),
                    "upper_wick_ratio": float(cstats.upper_wick_ratio),
                    "lower_wick_ratio": float(cstats.lower_wick_ratio),
                    "candle_body_size": float(cstats.body),
                    "candle_engulfing": bool(engulf),
                    "candle_pinbar": bool(pin_ok),
                },
            )
        )

    return out
