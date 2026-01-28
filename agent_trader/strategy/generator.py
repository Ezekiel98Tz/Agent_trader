from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from agent_trader.config import TradingConfig
from agent_trader.indicators.atr import atr, rolling_percentile
from agent_trader.market_regime.regime import classify_regime
from agent_trader.session.session_filter import get_session_state
from agent_trader.strategy.candles import candle_stats, is_bearish_engulfing, is_bullish_engulfing, is_pinbar
from agent_trader.strategy.fvg import detect_fvgs_m15, latest_relevant_fvg
from agent_trader.strategy.smc import detect_smc_features
from agent_trader.strategy.support_resistance import compute_sr_context, distance_to_nearest, nearest_level
from agent_trader.strategy.trend import compute_trend_context
from agent_trader.types import Side, TradeCandidate
from agent_trader.utils import infer_session, pips_to_price, price_to_pips, within_day_cutoff


@dataclass(frozen=True)
class CandidateInputs:
    h4: pd.DataFrame
    h1: pd.DataFrame
    m15: pd.DataFrame


def generate_candidates(data: CandidateInputs, *, cfg: TradingConfig, live_gate: bool = False, training_mode: bool = False) -> list[TradeCandidate]:
    m15 = data.m15.reset_index(drop=True)
    m15_times = pd.to_datetime(m15["time"])
    if live_gate and len(m15_times):
        latest_t = m15_times.iloc[-1].to_pydatetime()
        if get_session_state(latest_t, tz=cfg.timezone) == "BLOCKED":
            return []

    h4_ctx = compute_trend_context(data.h4)
    h1_ctx = compute_trend_context(data.h1)
    atr14 = atr(m15, 14)
    atr_pct = rolling_percentile(atr14, window=250)
    fvgs = detect_fvgs_m15(m15, min_gap=0.0)

    h4_times = pd.to_datetime(data.h4["time"])
    h1_times = pd.to_datetime(data.h1["time"])

    last_sr_h1_idx = -1
    sr = compute_sr_context(data.h1, end_time=None)

    out: list[TradeCandidate] = []
    for i in range(210, len(m15)):
        t = m15_times.iloc[i].to_pydatetime()
        
        # Default session values for training mode
        session = "London"
        overlap = True
        session_state = "PRIMARY"

        # During training, we ignore session filters to maximize data samples.
        # This helps the AI learn patterns even if they happen outside London hours.
        if not training_mode:
            session_state = get_session_state(t, tz=cfg.timezone, symbol=cfg.symbol, cfg=cfg)
            if session_state == "BLOCKED":
                continue
            if not within_day_cutoff(t, cfg.timezone, cfg.day_end_cutoff):
                continue
            session, overlap = infer_session(t, cfg.timezone)
            if session == "OffHours":
                continue

        close = float(m15.loc[i, "close"])
        h4_idx = int(h4_times.searchsorted(t, side="right") - 1)
        h1_idx = int(h1_times.searchsorted(t, side="right") - 1)
        if h4_idx < 0 or h1_idx < 0:
            continue

        h4_dir = str(h4_ctx.direction.iloc[h4_idx])
        h1_dir = str(h1_ctx.direction.iloc[h1_idx])
        atr_p = None if pd.isna(atr_pct.iloc[i]) else float(atr_pct.iloc[i])
        ema_slope = float(h1_ctx.ema50_slope.iloc[h1_idx])
        ema_align = float(h1_ctx.ema_alignment.iloc[h1_idx])
        regime = classify_regime(ema50_slope=ema_slope, ema_alignment=ema_align, atr_percentile=atr_p)
        
        # We allow TRANSITION regime if it's an SMC setup (CHoCH or OB)
        # Otherwise, the EMA-based trend/range logic might miss the very start of an institutional move.
        if regime == "TRANSITION":
            # Just peek at SMC features for this candle
            tmp_ms, tmp_obs = detect_smc_features(m15.iloc[max(0, i-100) : i+1])
            if not (tmp_ms.choch_occured or any(not ob.is_mitigated for ob in tmp_obs)):
                continue

        if h1_idx != last_sr_h1_idx:
            last_sr_h1_idx = h1_idx
            sr = compute_sr_context(data.h1, end_time=h1_times.iloc[h1_idx].to_pydatetime())

        prev = m15.loc[i - 1]
        cur = m15.loc[i]
        pin_ok, pin_side = is_pinbar(cur, min_wick_ratio=2.0)
        cstats = candle_stats(cur)

        n_sup = nearest_level(close, sr.supports, kind="support")
        n_res = nearest_level(close, sr.resistances, kind="resistance")
        d_sup = None if n_sup is None else n_sup[1]
        d_res = None if n_res is None else n_res[1]
        a14 = float(atr14.iloc[i]) if pd.notna(atr14.iloc[i]) else None

        # 2. SMC Analysis (M15 context)
        smc_ms, smc_obs = detect_smc_features(m15.iloc[max(0, i-100) : i+1])
        
        if regime == "TREND" or regime == "TRANSITION":
            # Determine primary direction based on H1 trend + SMC Structure
            if h1_dir == "up" or smc_ms.structure == "bullish":
                side = Side.BUY
            elif h1_dir == "down" or smc_ms.structure == "bearish":
                side = Side.SELL
            else:
                # If they contradict, we still try to find a setup but with lower confidence
                side = Side.BUY if h1_dir == "up" else Side.SELL
            
            engulf = is_bullish_engulfing(prev, cur) if side == Side.BUY else is_bearish_engulfing(prev, cur)
            candle_ok = engulf or (pin_ok and ((pin_side == "bull" and side == Side.BUY) or (pin_side == "bear" and side == Side.SELL)))
            
            momentum_ok = False
            if not candle_ok:
                if side == Side.BUY and cur["close"] > cur["open"] and cstats.body > (a14 * 0.4):
                    momentum_ok = True
                elif side == Side.SELL and cur["close"] < cur["open"] and cstats.body > (a14 * 0.4):
                    momentum_ok = True

            # If no candle or momentum signal, we check if we are hitting an Order Block
            in_ob = False
            for ob in smc_obs:
                if not ob.is_mitigated and ob.side == ("bullish" if side == Side.BUY else "bearish"):
                    if side == Side.BUY and cur["low"] <= ob.top and cur["close"] >= ob.bottom:
                        in_ob = True
                        break
                    elif side == Side.SELL and cur["high"] >= ob.bottom and cur["close"] <= ob.top:
                        in_ob = True
                        break

            # Now, instead of skipping, we just require at least ONE signal (Candle, Momentum, or OB)
            if not (candle_ok or momentum_ok or in_ob) and not training_mode:
                continue
            
            fvg_match = latest_relevant_fvg(m15, fvgs, idx=i, side=side, max_age_bars=96)
            
            if a14 is None:
                continue
            
            sl = close - pips_to_price(cfg.symbol, cfg.risk_sl_pips) if side == Side.BUY else close + pips_to_price(cfg.symbol, cfg.risk_sl_pips)
            if side == Side.BUY:
                tp_anchor = close + (d_res if d_res is not None else (a14 * 2.0))
            else:
                tp_anchor = close - (d_sup if d_sup is not None else (a14 * 2.0))
            tp = float(tp_anchor)
            rr = abs(tp - close) / abs(close - sl) if abs(close - sl) > 0 else 0.0
            
            # STRENGTH-BASED CONFLUENCE (The new "Expert" way)
            confluence = 0.0
            confluence += 1.0 if h1_dir != "range" else 0.5 # Trend presence
            confluence += 1.0 if h4_dir == h1_dir else 0.0 # Trend Alignment
            confluence += 1.0 if smc_ms.structure == ("bullish" if side == Side.BUY else "bearish") else 0.0 # SMC Alignment
            confluence += 1.5 if smc_ms.choch_occured else 0.0 # CHoCH is VERY strong
            confluence += 1.25 if in_ob else 0.0 # Order Block is strong
            confluence += 1.0 if (fvg_match and fvg_match.inside) else 0.0
            confluence += 0.5 if candle_ok else 0.0
            confluence += 0.5 if overlap else 0.0
            confluence += 0.25 if cstats.body > a14 * 0.25 else 0.0
            
            reason = "smc+choch" if smc_ms.choch_occured else ("smc+ob" if in_ob else "trend+priceaction")
            setup_type = "smc_institutional" if (smc_ms.choch_occured or in_ob) else "trend_follow"
            fvg_size = price_to_pips(cfg.symbol, fvg_match.fvg.size) if fvg_match else 0.0
            time_since_fvg = fvg_match.age_bars if fvg_match else 0
            fvg_inside = fvg_match.inside if fvg_match else False
        else:
            if a14 is None:
                continue
            
            # Loosened: In a range, we just need to be in the "buying zone" or "selling zone"
            near_support = d_sup is not None and d_sup <= (a14 * 2.0)
            near_res = d_res is not None and d_res <= (a14 * 2.0)
            
            # SMC Order Block as an alternative magnet
            near_ob = False
            for ob in smc_obs:
                if not ob.is_mitigated:
                    if ob.side == "bullish" and abs(close - ob.top) <= (a14 * 2.0):
                        near_ob = True
                        side = Side.BUY
                        break
                    elif ob.side == "bearish" and abs(close - ob.bottom) <= (a14 * 2.0):
                        near_ob = True
                        side = Side.SELL
                        break

            if not (near_support or near_res or near_ob) and not training_mode:
                continue
            
            if not near_ob:
                if near_support and (not near_res or (d_sup is not None and d_res is not None and d_sup <= d_res)):
                    side = Side.BUY
                else:
                    side = Side.SELL

            engulf = is_bullish_engulfing(prev, cur) if side == Side.BUY else is_bearish_engulfing(prev, cur)
            candle_ok = engulf or (pin_ok and ((pin_side == "bull" and side == Side.BUY) or (pin_side == "bear" and side == Side.SELL)))
            
            # Momentum fallback for range
            momentum_ok = False
            if not candle_ok:
                if side == Side.BUY and cur["close"] > cur["open"] and cstats.body > (a14 * 0.3):
                    momentum_ok = True
                elif side == Side.SELL and cur["close"] < cur["open"] and cstats.body > (a14 * 0.3):
                    momentum_ok = True

            # Require some form of signal
            if not (candle_ok or momentum_ok) and not training_mode:
                continue
            
            fvg_match = latest_relevant_fvg(m15, fvgs, idx=i, side=side, max_age_bars=96)
            sl = close - pips_to_price(cfg.symbol, cfg.risk_sl_pips) if side == Side.BUY else close + pips_to_price(cfg.symbol, cfg.risk_sl_pips)
            
            if side == Side.BUY:
                tp_anchor = (n_res[0].price if n_res is not None else (close + a14 * 2.0))
            else:
                tp_anchor = (n_sup[0].price if n_sup is not None else (close - a14 * 2.0))
            tp = float(tp_anchor)
            rr = abs(tp - close) / abs(close - sl) if abs(close - sl) > 0 else 0.0
            
            confluence = 0.0
            confluence += 1.0 # Base for range
            confluence += 1.0 if ((d_sup is not None and d_sup < a14) or (d_res is not None and d_res < a14)) else 0.0
            confluence += 1.25 if near_ob else 0.0
            confluence += 0.5 if candle_ok else 0.0
            confluence += 0.5 if overlap else 0.0
            confluence += 0.25 if cstats.body > a14 * 0.25 else 0.0
            confluence += 0.25 if (fvg_match is not None and fvg_match.inside) else 0.0
            
            reason = "range+smc_ob" if near_ob else ("range+momentum" if momentum_ok else "range+candle")
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
                    "smc_structure": smc_ms.structure,
                    "smc_choch": bool(smc_ms.choch_occured),
                    "smc_in_ob": bool(in_ob),
                },
            )
        )

    if live_gate and not out:
        # Diagnostic for the user
        last_idx = len(m15) - 1
        if last_idx >= 0:
            last_regime = classify_regime(
                ema50_slope=float(h1_ctx.ema50_slope.iloc[h1_idx]), 
                ema_alignment=float(h1_ctx.ema_alignment.iloc[h1_idx]), 
                atr_percentile=(None if pd.isna(atr_pct.iloc[last_idx]) else float(atr_pct.iloc[last_idx]))
            )
            # We don't print every time, maybe just a hint
            # print(f"DEBUG: Last bar regime: {last_regime}")

    return out
