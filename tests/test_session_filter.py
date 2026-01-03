from __future__ import annotations

from datetime import datetime, timezone

from agent_trader.session.session_filter import get_session_state


def test_session_primary():
    dt = datetime(2024, 1, 2, 12, 30, tzinfo=timezone.utc)
    assert get_session_state(dt) == "PRIMARY"


def test_session_secondary():
    dt = datetime(2024, 1, 2, 9, 0, tzinfo=timezone.utc)
    assert get_session_state(dt) == "SECONDARY"


def test_session_blocked():
    dt = datetime(2024, 1, 2, 19, 0, tzinfo=timezone.utc)
    assert get_session_state(dt) == "BLOCKED"

