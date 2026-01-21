from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

@dataclass(frozen=True)
class MarketStructure:
    last_high: float
    last_low: float
    structure: Literal["bullish", "bearish", "ranging"]
    choch_occured: bool

@dataclass(frozen=True)
class OrderBlock:
    top: float
    bottom: float
    side: Literal["bullish", "bearish"]
    is_mitigated: bool
    strength: float # Based on the move that followed

def detect_smc_features(df: pd.DataFrame, window: int = 20) -> tuple[MarketStructure, list[OrderBlock]]:
    """
    Detects Market Structure and Order Blocks from OHLC data.
    """
    if len(df) < window * 2:
        return MarketStructure(0, 0, "ranging", False), []

    # 1. Simple Market Structure
    recent = df.tail(window * 2)
    highs = recent["high"].rolling(window=5, center=True).max()
    lows = recent["low"].rolling(window=5, center=True).min()
    
    # Filter for actual swing points
    swing_highs = recent[recent["high"] == highs]["high"].tolist()
    swing_lows = recent[recent["low"] == lows]["low"].tolist()
    
    last_high = swing_highs[-1] if swing_highs else recent["high"].max()
    last_low = swing_lows[-1] if swing_lows else recent["low"].min()
    
    # CHoCH Detection (Simple version: price broke the last swing point in opposite direction)
    current_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2]
    
    choch = False
    structure: Literal["bullish", "bearish", "ranging"] = "ranging"
    
    if current_close > last_high and prev_close <= last_high:
        choch = True
        structure = "bullish"
    elif current_close < last_low and prev_close >= last_low:
        choch = True
        structure = "bearish"
    elif current_close > last_low and current_close < last_high:
        structure = "ranging"
    
    # 2. Order Block Detection
    # Logic: Look for the last opposite candle before a strong move (3+ large candles in same direction)
    obs = []
    for i in range(len(df) - 5, 5, -1):
        # Bullish OB: Last bearish candle before a strong upward move
        is_bear_candle = df.iloc[i]["close"] < df.iloc[i]["open"]
        if is_bear_candle:
            future_move = df.iloc[i+1 : i+4]
            # Strong move: 3 green candles or total move > ATR
            if (future_move["close"] > future_move["open"]).all():
                move_size = future_move["close"].iloc[-1] - df.iloc[i]["close"]
                obs.append(OrderBlock(
                    top=float(df.iloc[i]["high"]),
                    bottom=float(df.iloc[i]["low"]),
                    side="bullish",
                    is_mitigated=False,
                    strength=float(move_size)
                ))
                if len(obs) >= 3: break # Keep it light

        # Bearish OB: Last bullish candle before a strong downward move
        is_bull_candle = df.iloc[i]["close"] > df.iloc[i]["open"]
        if is_bull_candle:
            future_move = df.iloc[i+1 : i+4]
            if (future_move["close"] < future_move["open"]).all():
                move_size = df.iloc[i]["close"] - future_move["close"].iloc[-1]
                obs.append(OrderBlock(
                    top=float(df.iloc[i]["high"]),
                    bottom=float(df.iloc[i]["low"]),
                    side="bearish",
                    is_mitigated=False,
                    strength=float(move_size)
                ))
                if len(obs) >= 3: break

    # Check for mitigation (if current price has already touched the OB)
    final_obs = []
    for ob in obs:
        mitigated = (df["low"].tail(5).min() <= ob.top and df["high"].tail(5).max() >= ob.bottom)
        final_obs.append(OrderBlock(ob.top, ob.bottom, ob.side, mitigated, ob.strength))

    return MarketStructure(last_high, last_low, structure, choch), final_obs
