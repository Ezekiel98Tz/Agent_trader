from __future__ import annotations

import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def rolling_percentile(series: pd.Series, window: int = 250) -> pd.Series:
    def _pct(x):
        s = pd.Series(x)
        return (s.rank(pct=True).iloc[-1]) if len(s) else float("nan")

    return series.rolling(window, min_periods=window).apply(_pct, raw=False)

