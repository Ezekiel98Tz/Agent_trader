from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo


SessionState = Literal["PRIMARY", "SECONDARY", "BLOCKED"]

TZ_TANZANIA = ZoneInfo("Africa/Dar_es_Salaam")

PRIMARY_START = time(15, 30)
PRIMARY_END = time(20, 30)

SECONDARY_START = time(11, 30)
SECONDARY_END = time(14, 30)


def get_session_state(time_utc: datetime) -> SessionState:
    dt = time_utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(TZ_TANZANIA)
    t = local.time()

    if PRIMARY_START <= t < PRIMARY_END:
        return "PRIMARY"
    if SECONDARY_START <= t < SECONDARY_END:
        return "SECONDARY"
    return "BLOCKED"

