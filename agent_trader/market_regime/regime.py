from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MarketRegime = Literal["TREND", "RANGE", "TRANSITION"]


@dataclass(frozen=True)
class RegimeThresholds:
    ema_slope_trend: float = 0.00002
    ema_slope_range: float = 0.00001
    ema_alignment_trend: float = 0.00010
    ema_alignment_range: float = 0.00005
    atr_percentile_trend: float = 0.60
    atr_percentile_range: float = 0.40


DEFAULT_THRESHOLDS = RegimeThresholds()


def classify_regime(
    *,
    ema50_slope: float | None,
    ema_alignment: float | None,
    atr_percentile: float | None,
    th: RegimeThresholds = DEFAULT_THRESHOLDS,
) -> MarketRegime:
    if ema50_slope is None or ema_alignment is None or atr_percentile is None:
        return "TRANSITION"
    
    # Loosened: If there's enough volatility, we lean towards TREND
    if (
        abs(ema50_slope) >= th.ema_slope_range
        and atr_percentile >= 0.5
    ):
        return "TREND"
        
    # If it's very quiet, it's a RANGE
    if (
        atr_percentile <= th.atr_percentile_range
    ):
        return "RANGE"
        
    # Default to TREND if not extremely quiet, to allow the AI to find patterns
    if atr_percentile > 0.4:
        return "TREND"
        
    return "TRANSITION"

