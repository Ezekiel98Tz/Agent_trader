from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


def pip_value(symbol: str) -> float:
    if symbol.endswith("JPY"):
        return 0.01
    return 0.0001


def price_to_pips(symbol: str, price_delta: float) -> float:
    return price_delta / pip_value(symbol)


def pips_to_price(symbol: str, pips: float) -> float:
    return pips * pip_value(symbol)


def within_day_cutoff(dt: datetime, tz: ZoneInfo, cutoff: time) -> bool:
    local = dt.astimezone(tz)
    return local.time() <= cutoff


def infer_session(dt: datetime, tz: ZoneInfo) -> tuple[str, bool]:
    local = dt.astimezone(tz)
    t = local.time()
    asia = time(0, 0) <= t < time(7, 0)
    london = time(7, 0) <= t < time(13, 0)
    ny = time(13, 0) <= t < time(21, 0)
    overlap = time(13, 0) <= t < time(16, 0)
    if asia:
        return "Asia", overlap
    if london:
        return "London", overlap
    if ny:
        return "NY", overlap
    return "OffHours", overlap

