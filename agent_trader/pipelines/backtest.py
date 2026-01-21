from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agent_trader.backtest.engine import BacktestConfig, assert_safety, simulate_trades, summarize
from agent_trader.config import DEFAULT_CONFIG
from agent_trader.data.csv_loader import load_ohlcv_csv
from agent_trader.data.mt5_loader import load_rates, timeframe_from_str
from agent_trader.features.builder import build_feature_rows
from agent_trader.ml.model import load_model, predict_proba
from agent_trader.policy.quality import decide_quality
from agent_trader.strategy.generator import CandidateInputs, generate_candidates


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["csv", "mt5"], default="csv")
    ap.add_argument("--h4", default="")
    ap.add_argument("--h1", default="")
    ap.add_argument("--m15", default="")
    ap.add_argument("--symbol", default=DEFAULT_CONFIG.symbol)
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--model", required=True)
    ap.add_argument("--min-prob", type=float, default=0.60)
    ap.add_argument("--spread-pips", type=float, default=1.2)
    ap.add_argument("--fill-policy", choices=["sl_first", "tp_first", "ohlc_path"], default="ohlc_path")
    ap.add_argument("--max-hold-bars", type=int, default=48)
    ap.add_argument("--out-trades", default="")
    args = ap.parse_args()

    cfg = DEFAULT_CONFIG
    if args.source == "csv":
        if not args.h4 or not args.h1 or not args.m15:
            raise SystemExit("--h4/--h1/--m15 are required when --source=csv")
        h4 = load_ohlcv_csv(args.h4, schema="generic")
        h1 = load_ohlcv_csv(args.h1, schema="generic")
        m15 = load_ohlcv_csv(args.m15, schema="generic")
    else:
        if not args.start or not args.end:
            raise SystemExit("--start/--end are required when --source=mt5")
        start = _parse_dt(args.start)
        end = _parse_dt(args.end)
        symbol = str(args.symbol)
        h4 = load_rates(symbol=symbol, timeframe=timeframe_from_str("H4"), start=start, end=end, timezone="UTC")
        h1 = load_rates(symbol=symbol, timeframe=timeframe_from_str("H1"), start=start, end=end, timezone="UTC")
        m15 = load_rates(symbol=symbol, timeframe=timeframe_from_str("M15"), start=start, end=end, timezone="UTC")

    artifacts = load_model(str(args.model))
    candidates = generate_candidates(CandidateInputs(h4=h4, h1=h1, m15=m15), cfg=cfg, live_gate=False)
    feat_rows = build_feature_rows(cfg=cfg, h4=h4, h1=h1, m15=m15, candidates=candidates)
    if not feat_rows:
        print(json.dumps({"trades": 0, "reason": "no_candidates"}, separators=(",", ":")))
        return 0

    feat_df = pd.DataFrame([r.features for r in feat_rows])
    probs = predict_proba(artifacts, feat_df)

    best_by_time: dict[datetime, tuple[int, float]] = {}
    for idx, (cand, p) in enumerate(zip(candidates, probs)):
        p = float(p)
        if p < float(args.min_prob):
            continue
        prev = best_by_time.get(cand.time)
        if prev is None or p > prev[1]:
            best_by_time[cand.time] = (idx, p)

    selected: list = []
    for idx, p in best_by_time.values():
        cand = candidates[idx]
        regime = str(cand.meta.get("market_regime") or "TRANSITION")
        session_state = str(cand.meta.get("session_state") or "BLOCKED")
        decision = decide_quality(
            probability=float(p),
            confluence_score=float(cand.confluence_score),
            market_regime=regime,  # type: ignore[arg-type]
            session_state=session_state,  # type: ignore[arg-type]
            atr_percentile=cand.meta.get("atr_percentile"),
        )
        cand.meta["model_probability"] = float(p)
        cand.meta["quality"] = decision.quality
        cand.meta["risk_multiplier"] = float(decision.risk_multiplier)
        selected.append(cand)

    bt = BacktestConfig(spread_pips=float(args.spread_pips), max_hold_bars=int(args.max_hold_bars), fill_policy=str(args.fill_policy))
    results = simulate_trades(m15, selected, cfg=cfg, bt=bt)
    assert_safety(results, cfg=cfg)
    summ = summarize(results)
    print(json.dumps(asdict(summ), separators=(",", ":"), ensure_ascii=False, default=str))

    if args.out_trades:
        out_path = Path(args.out_trades)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(
            [
                {
                    "entry_time": r.entry_fill.time,
                    "exit_time": r.exit_fill.time,
                    "symbol": r.candidate.symbol,
                    "side": r.candidate.side.value,
                    "entry": r.entry_fill.price,
                    "exit": r.exit_fill.price,
                    "outcome": r.outcome,
                    "pnl_pips": r.pnl_pips,
                    "r_multiple": r.r_multiple,
                    "r_multiple_scaled": r.r_multiple_scaled,
                    "risk_multiplier": r.risk_multiplier,
                    "session_state": r.session_state,
                    "market_regime": r.market_regime,
                }
                for r in results
            ]
        )
        df.to_csv(out_path, index=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
