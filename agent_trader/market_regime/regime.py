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
    if (
        abs(ema50_slope) >= th.ema_slope_trend
        and abs(ema_alignment) >= th.ema_alignment_trend
        and atr_percentile >= th.atr_percentile_trend
    ):
        return "TREND"
    if (
        abs(ema50_slope) <= th.ema_slope_range
        and abs(ema_alignment) <= th.ema_alignment_range
        and atr_percentile <= th.atr_percentile_range
    ):
        return "RANGE"
    return "TRANSITION"

