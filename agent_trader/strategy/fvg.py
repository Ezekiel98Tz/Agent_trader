from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from agent_trader.types import FVG, Side


@dataclass(frozen=True)
class FVGMatch:
    fvg: FVG
    inside: bool
    age_bars: int


def detect_fvgs_m15(df_m15: pd.DataFrame, *, min_gap: float = 0.0) -> list[FVG]:
    df = df_m15.reset_index(drop=True)
    out: list[FVG] = []
    for i in range(2, len(df)):
        c1 = df.loc[i - 2]
        c2 = df.loc[i - 1]
        c3 = df.loc[i]
        up_gap = (c3["low"] - c1["high"]) > min_gap and c2["close"] > c2["open"]
        down_gap = (c1["low"] - c3["high"]) > min_gap and c2["close"] < c2["open"]
        if up_gap:
            out.append(
                FVG(
                    start_time=pd.to_datetime(c1["time"]).to_pydatetime(),
                    end_time=pd.to_datetime(c3["time"]).to_pydatetime(),
                    top=float(c3["low"]),
                    bottom=float(c1["high"]),
                    direction=Side.BUY,
                )
            )
        if down_gap:
            out.append(
                FVG(
                    start_time=pd.to_datetime(c1["time"]).to_pydatetime(),
                    end_time=pd.to_datetime(c3["time"]).to_pydatetime(),
                    top=float(c1["low"]),
                    bottom=float(c3["high"]),
                    direction=Side.SELL,
                )
            )
    return out


def latest_relevant_fvg(
    df_m15: pd.DataFrame,
    fvgs: list[FVG],
    *,
    idx: int,
    side: Side,
    max_age_bars: int = 96,
) -> FVGMatch | None:
    if not fvgs:
        return None
    row = df_m15.iloc[idx]
    price = float(row["close"])
    t = pd.to_datetime(row["time"]).to_pydatetime()
    candidates = [f for f in fvgs if f.direction == side and f.end_time <= t]
    if not candidates:
        return None
    candidates.sort(key=lambda f: f.end_time, reverse=True)
    for f in candidates:
        age = int((t - f.end_time).total_seconds() // (15 * 60))
        if age > max_age_bars:
            return None
        inside = f.bottom <= price <= f.top if f.direction == Side.BUY else f.bottom <= price <= f.top
        return FVGMatch(fvg=f, inside=inside, age_bars=age)
    return None

