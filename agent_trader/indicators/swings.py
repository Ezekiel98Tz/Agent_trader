from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SwingPoint:
    idx: int
    time: object
    price: float
    kind: str


def find_swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> list[SwingPoint]:
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    times = df["time"].to_numpy()
    out: list[SwingPoint] = []
    n = len(df)
    for i in range(left, n - right):
        h = highs[i]
        if h == max(highs[i - left : i + right + 1]):
            out.append(SwingPoint(i, times[i], float(h), "high"))
        l = lows[i]
        if l == min(lows[i - left : i + right + 1]):
            out.append(SwingPoint(i, times[i], float(l), "low"))
    out.sort(key=lambda s: s.idx)
    return out

