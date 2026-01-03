from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TradingConfig:
    symbol: str = "GBPUSD"
    risk_sl_pips: float = 17.5
    max_hold_minutes: int = 6 * 60
    allow_overnight: bool = False
    timezone: ZoneInfo = ZoneInfo("Europe/London")
    day_end_cutoff: time = time(21, 30)
    min_rr: float = 1.2
    max_trades_per_week: int = 5


DEFAULT_CONFIG = TradingConfig()

