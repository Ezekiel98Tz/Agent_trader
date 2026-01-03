from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd


class MT5NotAvailable(RuntimeError):
    pass


def _require_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise MT5NotAvailable("MetaTrader5 Python package is not available") from e
    return mt5


def load_rates(
    *,
    symbol: str,
    timeframe: int,
    start: datetime,
    end: datetime,
    timezone: Optional[str] = "UTC",
) -> pd.DataFrame:
    mt5 = _require_mt5()
    if not mt5.initialize():
        raise RuntimeError("mt5.initialize() failed")
    try:
        rates = mt5.copy_rates_range(symbol, timeframe, start, end)
        if rates is None:
            raise RuntimeError("mt5.copy_rates_range returned None")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        if timezone and timezone != "UTC":
            df["time"] = df["time"].dt.tz_convert(timezone)
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["time", "open", "high", "low", "close", "volume"]].copy()
    finally:
        mt5.shutdown()

