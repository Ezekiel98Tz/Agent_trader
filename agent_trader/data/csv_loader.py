from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import pandas as pd


def load_ohlcv_csv(
    path: str | Path,
    *,
    time_col: str = "time",
    tz: Optional[str] = "UTC",
    schema: Literal["mt5", "generic"] = "generic",
) -> pd.DataFrame:
    p = Path(path)
    df = pd.read_csv(p)
    if time_col not in df.columns:
        raise ValueError(f"Missing '{time_col}' column in {p}")
    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="raise")
    if tz and tz != "UTC":
        df[time_col] = df[time_col].dt.tz_convert(tz)
    rename = {}
    if schema == "mt5":
        rename = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "tick_volume": "volume",
        }
    if rename:
        df = df.rename(columns=rename)
    needed = ["open", "high", "low", "close"]
    for c in needed:
        if c not in df.columns:
            raise ValueError(f"Missing '{c}' column in {p}")
    if "volume" not in df.columns:
        df["volume"] = 0
    df = df[[time_col, "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values(time_col).reset_index(drop=True)
    df = df.rename(columns={time_col: "time"})
    return df

