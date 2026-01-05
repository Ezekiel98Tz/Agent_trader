from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from agent_trader.config import TradingConfig
from agent_trader.strategy.trend import compute_trend_context
from agent_trader.types import TradeCandidate
from agent_trader.utils import infer_session, price_to_pips


@dataclass(frozen=True)
class FeatureRow:
    time: object
    features: dict[str, float | int | str | None]


def build_feature_rows(
    *,
    cfg: TradingConfig,
    h4: pd.DataFrame,
    h1: pd.DataFrame,
    m15: pd.DataFrame,
    candidates: list[TradeCandidate],
) -> list[FeatureRow]:
    h4_ctx = compute_trend_context(h4)
    h1_ctx = compute_trend_context(h1)
    m15 = m15.reset_index(drop=True)
    time_index = pd.to_datetime(m15["time"])
    idx_by_time = {t.to_pydatetime(): i for i, t in enumerate(time_index)}
    h4_times = pd.to_datetime(h4["time"])
    h1_times = pd.to_datetime(h1["time"])

    rows: list[FeatureRow] = []
    for c in candidates:
        i = idx_by_time.get(c.time)
        if i is None or i <= 1:
            continue
        row = m15.loc[i]
        prev = m15.loc[i - 1]
        session, overlap = infer_session(c.time, cfg.timezone)
        
        # Preserve timezone awareness for comparison
        t_compare = pd.to_datetime(c.time)
        h4_idx = int(h4_times.searchsorted(t_compare, side="right") - 1)
        h1_idx = int(h1_times.searchsorted(t_compare, side="right") - 1)
        if h4_idx < 0 or h1_idx < 0:
            continue
        sl_pips = price_to_pips(cfg.symbol, abs(c.entry_price - c.sl_price))
        tp_pips = price_to_pips(cfg.symbol, abs(c.tp_price - c.entry_price))
        rr = tp_pips / sl_pips if sl_pips else None

        meta = c.meta
        f: dict[str, float | int | str | None] = {
            "symbol": c.symbol,
            "side": c.side.value,
            "price_vs_ema50_h4": float(h4_ctx.price_vs_ema50.iloc[h4_idx]),
            "ema_slope_h4": float(h4_ctx.ema50_slope.iloc[h4_idx]),
            "ema_alignment_h4": float(h4_ctx.ema_alignment.iloc[h4_idx]),
            "price_vs_ema50_h1": float(h1_ctx.price_vs_ema50.iloc[h1_idx]),
            "ema_slope_h1": float(h1_ctx.ema50_slope.iloc[h1_idx]),
            "ema_alignment_h1": float(h1_ctx.ema_alignment.iloc[h1_idx]),
            "atr_14_pips": meta.get("atr14_pips"),
            "atr_percentile": meta.get("atr_percentile"),
            "session": session,
            "session_overlap": int(bool(overlap)),
            "session_state": meta.get("session_state"),
            "distance_to_support_pips": meta.get("distance_to_support_pips"),
            "distance_to_resistance_pips": meta.get("distance_to_resistance_pips"),
            "support_touch_count": meta.get("support_touch_count"),
            "resistance_touch_count": meta.get("resistance_touch_count"),
            "market_regime": meta.get("market_regime"),
            "setup_type": meta.get("setup_type"),
            "fvg_exists": 1,
            "fvg_size": meta.get("fvg_size"),
            "time_since_fvg": meta.get("time_since_fvg_bars"),
            "candle_body_size": meta.get("candle_body_size"),
            "upper_wick_ratio": meta.get("upper_wick_ratio"),
            "lower_wick_ratio": meta.get("lower_wick_ratio"),
            "confluence_score": c.confluence_score,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "rr_ratio": rr,
            "prev_close": float(prev["close"]),
            "cur_close": float(row["close"]),
        }
        rows.append(FeatureRow(time=c.time, features=f))
    return rows
