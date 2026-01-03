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


def _timeframe_from_str(mt5, timeframe: str) -> int:
    tf = timeframe.upper()
    m = {
        "M1": "TIMEFRAME_M1",
        "M5": "TIMEFRAME_M5",
        "M15": "TIMEFRAME_M15",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H4": "TIMEFRAME_H4",
        "D1": "TIMEFRAME_D1",
    }
    if tf not in m:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return int(getattr(mt5, m[tf]))


def timeframe_from_str(timeframe: str) -> int:
    mt5 = _require_mt5()
    return _timeframe_from_str(mt5, timeframe)


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


def load_rates_recent(
    *,
    symbol: str,
    timeframe: int,
    bars: int,
    timezone: Optional[str] = "UTC",
) -> pd.DataFrame:
    mt5 = _require_mt5()
    if bars <= 0:
        raise ValueError("bars must be > 0")
    if not mt5.initialize():
        raise RuntimeError("mt5.initialize() failed")
    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, int(bars))
        if rates is None:
            raise RuntimeError("mt5.copy_rates_from_pos returned None")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        if timezone and timezone != "UTC":
            df["time"] = df["time"].dt.tz_convert(timezone)
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["time", "open", "high", "low", "close", "volume"]].copy()
    finally:
        mt5.shutdown()


def load_recent_multi_timeframe(
    *,
    symbol: str,
    timeframes: dict[str, int] | None = None,
    bars_by_tf: dict[str, int] | None = None,
    timezone: Optional[str] = "UTC",
) -> dict[str, pd.DataFrame]:
    mt5 = _require_mt5()
    tfs = timeframes or {
        "M15": _timeframe_from_str(mt5, "M15"),
        "H1": _timeframe_from_str(mt5, "H1"),
        "H4": _timeframe_from_str(mt5, "H4"),
    }
    bars_map = bars_by_tf or {"M15": 1500, "H1": 800, "H4": 500}
    if not mt5.initialize():
        raise RuntimeError("mt5.initialize() failed")
    try:
        out: dict[str, pd.DataFrame] = {}
        for name, tf in tfs.items():
            bars = int(bars_map.get(name, 500))
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
            if rates is None:
                raise RuntimeError(f"mt5.copy_rates_from_pos returned None for {name}")
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            if timezone and timezone != "UTC":
                df["time"] = df["time"].dt.tz_convert(timezone)
            df = df.rename(columns={"tick_volume": "volume"})
            out[name] = df[["time", "open", "high", "low", "close", "volume"]].copy()
        return out
    finally:
        mt5.shutdown()


def get_spread_pips(*, symbol: str, pip_size: float) -> float:
    mt5 = _require_mt5()
    if not mt5.initialize():
        raise RuntimeError("mt5.initialize() failed")
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("mt5.symbol_info_tick returned None")
        spread = float(tick.ask) - float(tick.bid)
        return float(spread / float(pip_size))
    finally:
        mt5.shutdown()
