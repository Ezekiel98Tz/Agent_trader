from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from agent_trader.indicators.ema import ema, ema_slope


@dataclass(frozen=True)
class TrendContext:
    ema50: pd.Series
    ema200: pd.Series
    price_vs_ema50: pd.Series
    ema50_slope: pd.Series
    ema_alignment: pd.Series
    direction: pd.Series


def compute_trend_context(df: pd.DataFrame) -> TrendContext:
    close = df["close"]
    e50 = ema(close, 50)
    e200 = ema(close, 200)
    price_vs = (close - e50) / e50
    slope = ema_slope(e50, lookback=5)
    alignment = (e50 - e200) / e200
    direction = pd.Series(index=df.index, dtype="object")
    direction[(close > e50) & (e50 > e200) & (slope > 0)] = "up"
    direction[(close < e50) & (e50 < e200) & (slope < 0)] = "down"
    direction = direction.fillna("range")
    return TrendContext(
        ema50=e50,
        ema200=e200,
        price_vs_ema50=price_vs,
        ema50_slope=slope,
        ema_alignment=alignment,
        direction=direction,
    )

