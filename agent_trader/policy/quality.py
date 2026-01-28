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
    atr_percentile: float | None = None,
) -> QualityDecision:
    # 1. Basic filtering by regime
    # We now allow TRANSITION if it's a high-confluence SMC setup
    if market_regime == "TRANSITION" and confluence_score < 4.0:
        return QualityDecision(quality="SKIP", risk_multiplier=0.0)
    
    # 2. Strict blocking
    if session_state == "BLOCKED":
        return QualityDecision(quality="SKIP", risk_multiplier=0.0)

    # 3. Base Quality Classification
    # We use a combination of AI probability and Technical confluence
    
    # NEW: Strategy Strength Overrides (Allowing trades with low AI prob if Confluence is high)
    # GOOD: Extreme technical strength (Institutional/SMC)
    if confluence_score >= 4.0:
        base = QualityDecision(quality="GOOD", risk_multiplier=1.0)
    # GOOD: Strong technicals + some AI agreement
    elif (probability >= 0.50 and confluence_score >= 3.0) or (confluence_score >= 3.5):
        base = QualityDecision(quality="GOOD", risk_multiplier=0.75)
    # AVERAGE: Standard setups
    elif (probability >= 0.45 and confluence_score >= 2.5) or (confluence_score >= 3.0):
        base = QualityDecision(quality="AVERAGE", risk_multiplier=0.5)
    # FALLBACK: Normal AI-driven logic
    elif probability >= 0.60 and confluence_score >= 1.5:
        base = QualityDecision(quality="AVERAGE", risk_multiplier=0.5)
    else:
        base = QualityDecision(quality="SKIP", risk_multiplier=0.0)

    # 4. Market Activity Override (The "Smarter Way")
    # If volatility is high, we are more lenient with session rules
    is_highly_active = atr_percentile is not None and atr_percentile >= 0.7
    
    # 5. Session Logic
    if session_state == "PRIMARY":
        return base
        
    if session_state == "SECONDARY":
        # In secondary sessions, we usually only want GOOD trades.
        # But if the market is HIGHLY ACTIVE, we allow AVERAGE trades too.
        if is_highly_active:
            if base.quality == "SKIP":
                return QualityDecision(quality="SKIP", risk_multiplier=0.0)
            # Allow both GOOD and AVERAGE, but with reduced risk (half of base)
            return QualityDecision(quality=base.quality, risk_multiplier=base.risk_multiplier * 0.5)
        else:
            # Normal secondary session logic: only GOOD trades
            if base.quality != "GOOD":
                return QualityDecision(quality="SKIP", risk_multiplier=0.0)
            return QualityDecision(quality="GOOD", risk_multiplier=base.risk_multiplier * 0.5)

    return QualityDecision(quality="SKIP", risk_multiplier=0.0)
