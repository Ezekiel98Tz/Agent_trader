from __future__ import annotations

from agent_trader.policy.quality import decide_quality


def test_policy_skips_transition():
    d = decide_quality(probability=0.99, confluence_score=10.0, market_regime="TRANSITION", session_state="PRIMARY")
    assert d.quality == "SKIP"
    assert d.risk_multiplier == 0.0


def test_policy_secondary_allows_only_good_normally():
    # Average trade in secondary session (not highly active) -> SKIP
    d1 = decide_quality(probability=0.60, confluence_score=3.5, market_regime="TREND", session_state="SECONDARY", atr_percentile=0.3)
    assert d1.quality == "SKIP"
    assert d1.risk_multiplier == 0.0
    
    # Good trade in secondary session -> GOOD (with reduced risk)
    d2 = decide_quality(probability=0.80, confluence_score=5.0, market_regime="TREND", session_state="SECONDARY", atr_percentile=0.3)
    assert d2.quality == "GOOD"
    assert d2.risk_multiplier == 0.5


def test_policy_secondary_allows_average_if_highly_active():
    # Average trade in secondary session (HIGHLY ACTIVE) -> AVERAGE (with reduced risk)
    # Confluence 2.5 is now enough for AVERAGE
    d = decide_quality(probability=0.60, confluence_score=2.5, market_regime="TREND", session_state="SECONDARY", atr_percentile=0.8)
    assert d.quality == "AVERAGE"
    assert d.risk_multiplier == 0.25  # 0.5 * 0.5
