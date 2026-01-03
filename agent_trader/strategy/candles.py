from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CandleStats:
    body: float
    upper_wick: float
    lower_wick: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    direction: int


def candle_stats(row: pd.Series) -> CandleStats:
    o = float(row["open"])
    h = float(row["high"])
    l = float(row["low"])
    c = float(row["close"])
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    denom = body if body > 0 else (h - l if (h - l) > 0 else 1.0)
    return CandleStats(
        body=body,
        upper_wick=upper,
        lower_wick=lower,
        upper_wick_ratio=upper / denom,
        lower_wick_ratio=lower / denom,
        direction=1 if c > o else (-1 if c < o else 0),
    )


def is_bullish_engulfing(prev: pd.Series, cur: pd.Series) -> bool:
    return float(prev["close"]) < float(prev["open"]) and float(cur["close"]) > float(cur["open"]) and float(cur["close"]) >= float(prev["open"]) and float(cur["open"]) <= float(prev["close"])


def is_bearish_engulfing(prev: pd.Series, cur: pd.Series) -> bool:
    return float(prev["close"]) > float(prev["open"]) and float(cur["close"]) < float(cur["open"]) and float(cur["close"]) <= float(prev["open"]) and float(cur["open"]) >= float(prev["close"])


def is_pinbar(row: pd.Series, *, min_wick_ratio: float = 2.0) -> tuple[bool, str]:
    s = candle_stats(row)
    bull = s.lower_wick_ratio >= min_wick_ratio and s.direction >= 0
    bear = s.upper_wick_ratio >= min_wick_ratio and s.direction <= 0
    if bull and not bear:
        return True, "bull"
    if bear and not bull:
        return True, "bear"
    return False, "none"

