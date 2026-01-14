from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo


from agent_trader.config import DEFAULT_CONFIG, TradingConfig

SessionState = Literal["PRIMARY", "SECONDARY", "BLOCKED"]

TZ_LONDON = ZoneInfo("Europe/London")


def get_session_state(
    time_utc: datetime, 
    tz: ZoneInfo | None = None, 
    symbol: str = "GBPUSD",
    cfg: TradingConfig = DEFAULT_CONFIG
) -> SessionState:
    dt = time_utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Use provided timezone or fallback to London as default for this project
    target_tz = tz if tz is not None else TZ_LONDON
    local = dt.astimezone(target_tz)
    t = local.time()

    # Default Windows from Config
    p_start, p_end = cfg.primary_start, cfg.primary_end
    s_start, s_end = cfg.secondary_start, cfg.secondary_end

    # USDCAD Specifics: New York Open is more important
    # We check for CAD specifically to avoid matching GBPUSD
    if "CAD" in symbol.upper():
        p_start = cfg.usd_cad_primary_start
        s_start = cfg.usd_cad_secondary_start
        s_end = cfg.usd_cad_secondary_end

    if p_start <= t < p_end:
        return "PRIMARY"
    if s_start <= t < s_end:
        return "SECONDARY"
    return "BLOCKED"

