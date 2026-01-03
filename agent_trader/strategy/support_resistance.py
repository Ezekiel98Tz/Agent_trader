from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd

from agent_trader.indicators.swings import find_swings
from agent_trader.types import SwingLevel


@dataclass(frozen=True)
class SRContext:
    supports: list[SwingLevel]
    resistances: list[SwingLevel]


def _cluster_levels(levels: list[tuple[datetime, float]], tolerance: float) -> list[SwingLevel]:
    if not levels:
        return []
    levels = sorted(levels, key=lambda x: x[1])
    clusters: list[list[tuple[datetime, float]]] = [[levels[0]]]
    for t, p in levels[1:]:
        if abs(p - clusters[-1][-1][1]) <= tolerance:
            clusters[-1].append((t, p))
        else:
            clusters.append([(t, p)])
    out: list[SwingLevel] = []
    for c in clusters:
        prices = np.array([p for _, p in c], dtype=float)
        price = float(prices.mean())
        touched = len(c)
        last_t, _ = max(c, key=lambda x: x[0])
        kind = "support"
        out.append(SwingLevel(price=price, touched=touched, last_touch_time=last_t, kind=kind))
    return out


def compute_sr_context(
    df_h1: pd.DataFrame,
    *,
    lookback_bars: int = 300,
    swing_left: int = 3,
    swing_right: int = 3,
    tolerance: float | None = None,
    end_time: datetime | None = None,
) -> SRContext:
    df_all = df_h1
    if end_time is not None:
        t = pd.to_datetime(end_time)
        df_all = df_h1[pd.to_datetime(df_h1["time"]) <= t]
    df = df_all.tail(lookback_bars).reset_index(drop=True)
    if len(df) < (swing_left + swing_right + 5):
        return SRContext(supports=[], resistances=[])
    swings = find_swings(df, left=swing_left, right=swing_right)
    typical_range = float((df["high"] - df["low"]).rolling(20).mean().iloc[-1])
    tol = tolerance if tolerance is not None else typical_range * 0.8
    highs: list[tuple[datetime, float]] = []
    lows: list[tuple[datetime, float]] = []
    for s in swings:
        t = pd.to_datetime(df.loc[s.idx, "time"]).to_pydatetime()
        if s.kind == "high":
            highs.append((t, s.price))
        else:
            lows.append((t, s.price))
    resistances = _cluster_levels(highs, tol)
    supports = _cluster_levels(lows, tol)
    resistances = [SwingLevel(l.price, l.touched, l.last_touch_time, "resistance") for l in resistances]
    return SRContext(supports=supports, resistances=resistances)


def distance_to_nearest(
    price: float,
    levels: list[SwingLevel],
    *,
    kind: Literal["support", "resistance"],
) -> float | None:
    candidates = [l.price for l in levels if l.kind == kind]
    if not candidates:
        return None
    if kind == "support":
        below = [p for p in candidates if p <= price]
        if not below:
            return None
        return price - max(below)
    above = [p for p in candidates if p >= price]
    if not above:
        return None
    return min(above) - price


def nearest_level(
    price: float,
    levels: list[SwingLevel],
    *,
    kind: Literal["support", "resistance"],
) -> tuple[SwingLevel, float] | None:
    filtered = [l for l in levels if l.kind == kind]
    if not filtered:
        return None
    if kind == "support":
        below = [l for l in filtered if l.price <= price]
        if not below:
            return None
        lvl = max(below, key=lambda l: l.price)
        return lvl, price - lvl.price
    above = [l for l in filtered if l.price >= price]
    if not above:
        return None
    lvl = min(above, key=lambda l: l.price)
    return lvl, lvl.price - price
