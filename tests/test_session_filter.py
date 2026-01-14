from __future__ import annotations

from datetime import datetime, timezone

from agent_trader.session.session_filter import get_session_state


def test_session_primary():
    # 16:30 London is PRIMARY for GBPUSD
    dt = datetime(2024, 1, 2, 16, 30, tzinfo=timezone.utc)
    assert get_session_state(dt, symbol="GBPUSD") == "PRIMARY"


def test_session_secondary():
    # 12:30 London is SECONDARY for GBPUSD
    dt = datetime(2024, 1, 2, 12, 30, tzinfo=timezone.utc)
    assert get_session_state(dt, symbol="GBPUSD") == "SECONDARY"


def test_session_usdcad_primary():
    # 13:30 London is PRIMARY for USDCAD (NY Open)
    dt = datetime(2024, 1, 2, 13, 30, tzinfo=timezone.utc)
    assert get_session_state(dt, symbol="USDCAD") == "PRIMARY"


def test_session_blocked():
    # 22:00 London is BLOCKED
    dt = datetime(2024, 1, 2, 22, 0, tzinfo=timezone.utc)
    assert get_session_state(dt) == "BLOCKED"

