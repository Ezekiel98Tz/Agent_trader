from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_trader.market_regime.regime import MarketRegime
from agent_trader.session.session_filter import SessionState


Quality = Literal["GOOD", "AVERAGE", "SKIP"]


@dataclass(frozen=True)
class QualityDecision:
    quality: Quality
    risk_multiplier: float


def decide_quality(
    *,
    probability: float,
    confluence_score: float,
    market_regime: MarketRegime,
    session_state: SessionState,
) -> QualityDecision:
    if market_regime == "TRANSITION":
        return QualityDecision(quality="SKIP", risk_multiplier=0.0)
    if session_state == "BLOCKED":
        return QualityDecision(quality="SKIP", risk_multiplier=0.0)
    if probability >= 0.65 and confluence_score >= 4.0 and market_regime == "TREND":
        base = QualityDecision(quality="GOOD", risk_multiplier=1.0)
    elif probability >= 0.62 and confluence_score >= 4.0 and market_regime == "RANGE":
        base = QualityDecision(quality="GOOD", risk_multiplier=0.75)
    elif probability >= 0.60 and confluence_score >= 3.0:
        base = QualityDecision(quality="AVERAGE", risk_multiplier=0.5)
    else:
        base = QualityDecision(quality="SKIP", risk_multiplier=0.0)

    if session_state == "PRIMARY":
        return base
    if session_state == "SECONDARY":
        if base.quality != "GOOD":
            return QualityDecision(quality="SKIP", risk_multiplier=0.0)
        return QualityDecision(quality="GOOD", risk_multiplier=min(base.risk_multiplier, 0.5))
    return QualityDecision(quality="SKIP", risk_multiplier=0.0)
