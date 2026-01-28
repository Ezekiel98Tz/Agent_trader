from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import pandas as pd
import time


def load_ohlcv_csv(
    path: str | Path,
    *,
    time_col: str = "time",
    tz: Optional[str] = "UTC",
    schema: Literal["mt5", "generic"] = "generic",
) -> pd.DataFrame:
    p = Path(path)
    # Add retry logic for locked files (common in MT4/MT5)
    retries = 3
    while retries > 0:
        try:
            df = pd.read_csv(p)
            break
        except (PermissionError, pd.errors.EmptyDataError):
            retries -= 1
            if retries == 0:
                raise
            time.sleep(0.5)
    if time_col not in df.columns:
        raise ValueError(f"Missing '{time_col}' column in {p}")
    # interpretation as naive (Broker Time)
    df[time_col] = pd.to_datetime(df[time_col], errors="raise")
    if tz and tz != "UTC":
        # If user explicitly wants conversion, they can provide tz
        df[time_col] = df[time_col].dt.tz_localize("UTC").dt.tz_convert(tz)
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

