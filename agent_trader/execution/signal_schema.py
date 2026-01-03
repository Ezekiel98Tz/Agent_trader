from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class TradeSignal:
    id: str
    time_utc: datetime
    symbol: str
    side: Literal["buy", "sell"]
    entry: float
    sl: float
    tp: float
    confluence: float
    model_probability: float
    session_state: Literal["PRIMARY", "SECONDARY"]
    market_regime: Literal["TREND", "RANGE", "TRANSITION"]
    quality: Literal["GOOD", "AVERAGE", "SKIP"]
    risk_multiplier: float
    mode: Literal["live", "paper", "visual"]
