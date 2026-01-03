from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | int | None = None


@dataclass(frozen=True)
class SwingLevel:
    price: float
    touched: int
    last_touch_time: datetime
    kind: str


@dataclass(frozen=True)
class FVG:
    start_time: datetime
    end_time: datetime
    top: float
    bottom: float
    direction: Side

    @property
    def size(self) -> float:
        return abs(self.top - self.bottom)


@dataclass(frozen=True)
class TradeCandidate:
    time: datetime
    symbol: str
    side: Side
    entry_price: float
    sl_price: float
    tp_price: float
    reason: str
    confluence_score: float
    meta: dict


@dataclass(frozen=True)
class LabeledTrade:
    candidate: TradeCandidate
    label: str
    mfe_pips: float
    mae_pips: float
    minutes_to_outcome: int
    outcome_price: Optional[float]

