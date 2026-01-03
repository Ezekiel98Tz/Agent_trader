from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def ema_slope(series: pd.Series, lookback: int = 5) -> pd.Series:
    return series.diff(lookback) / lookback

