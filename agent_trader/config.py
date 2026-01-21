from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TradingConfig:
    symbol: str = "GBPUSD"
    
    # Risk Management
    risk_sl_pips: float = 17.5
    risk_percent_per_trade: float = 1.0  # Percentage of account to risk (if EA supports)
    min_rr: float = 1.2
    max_signals_per_day: int = 10
    max_trades_per_week: int = 30
    max_spread_pips: float = 2.5
    
    # Session Timing (London Time / UTC+0)
    primary_start: time = time(15, 30)
    primary_end: time = time(20, 30)
    secondary_start: time = time(11, 30)
    secondary_end: time = time(14, 30)

    # USDCAD Specific Overrides (London Time)
    usd_cad_primary_start: time = time(13, 0)
    usd_cad_secondary_start: time = time(11, 0)
    usd_cad_secondary_end: time = time(13, 0)

    # Operational
    max_hold_minutes: int = 6 * 60
    allow_overnight: bool = False
    timezone: ZoneInfo = ZoneInfo("Europe/London")
    day_end_cutoff: time = time(21, 30)


DEFAULT_CONFIG = TradingConfig()
