from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from agent_trader.config import TradingConfig
from agent_trader.types import LabeledTrade, Side, TradeCandidate
from agent_trader.utils import price_to_pips, within_day_cutoff


@dataclass(frozen=True)
class LabelingResult:
    labeled: list[LabeledTrade]
    dropped: int


def label_candidates(
    *,
    cfg: TradingConfig,
    m15: pd.DataFrame,
    candidates: list[TradeCandidate],
    max_lookahead_bars: int = 48,
    break_even_after_rr: float = 1.0,
    break_even_label: str = "breakeven",
) -> LabelingResult:
    m15 = m15.reset_index(drop=True)
    time_index = pd.to_datetime(m15["time"])
    idx_by_time = {t.to_pydatetime(): i for i, t in enumerate(time_index)}

    labeled: list[LabeledTrade] = []
    dropped = 0
    for c in candidates:
        start_idx = idx_by_time.get(c.time)
        if start_idx is None:
            dropped += 1
            continue
        if not within_day_cutoff(c.time, cfg.timezone, cfg.day_end_cutoff):
            dropped += 1
            continue
        sl = c.sl_price
        tp = c.tp_price
        entry = c.entry_price
        sl_pips = price_to_pips(cfg.symbol, abs(entry - sl))
        tp_pips = price_to_pips(cfg.symbol, abs(tp - entry))
        be_trigger = entry + (tp - entry) * (break_even_after_rr * (sl_pips / tp_pips)) if tp_pips else None

        mfe = 0.0
        mae = 0.0
        outcome: str | None = None
        outcome_price: float | None = None
        minutes = 0
        be_armed = False
        for j in range(start_idx + 1, min(len(m15), start_idx + 1 + max_lookahead_bars)):
            row = m15.loc[j]
            t = pd.to_datetime(row["time"]).to_pydatetime()
            if not cfg.allow_overnight and t.date() != c.time.date():
                outcome = break_even_label
                outcome_price = entry
                minutes = int((t - c.time).total_seconds() // 60)
                break
            hi = float(row["high"])
            lo = float(row["low"])

            if c.side == Side.BUY:
                mfe = max(mfe, price_to_pips(cfg.symbol, hi - entry))
                mae = min(mae, price_to_pips(cfg.symbol, lo - entry))
                if be_trigger is not None and hi >= be_trigger:
                    be_armed = True
                hit_sl = lo <= sl
                hit_tp = hi >= tp
            else:
                mfe = max(mfe, price_to_pips(cfg.symbol, entry - lo))
                mae = min(mae, price_to_pips(cfg.symbol, entry - hi))
                if be_trigger is not None and lo <= be_trigger:
                    be_armed = True
                hit_sl = hi >= sl
                hit_tp = lo <= tp

            if hit_sl and hit_tp:
                outcome = "loss"
                outcome_price = sl
                minutes = int((t - c.time).total_seconds() // 60)
                break
            if hit_tp:
                outcome = "win"
                outcome_price = tp
                minutes = int((t - c.time).total_seconds() // 60)
                break
            if hit_sl:
                if be_armed:
                    outcome = break_even_label
                    outcome_price = entry
                else:
                    outcome = "loss"
                    outcome_price = sl
                minutes = int((t - c.time).total_seconds() // 60)
                break

        if outcome is None:
            last_t = pd.to_datetime(m15.loc[min(len(m15) - 1, start_idx + max_lookahead_bars), "time"]).to_pydatetime()
            outcome = break_even_label
            outcome_price = entry
            minutes = int((last_t - c.time).total_seconds() // 60)

        labeled.append(
            LabeledTrade(
                candidate=c,
                label=outcome,
                mfe_pips=float(mfe),
                mae_pips=float(mae),
                minutes_to_outcome=int(minutes),
                outcome_price=outcome_price,
            )
        )

    return LabelingResult(labeled=labeled, dropped=dropped)

