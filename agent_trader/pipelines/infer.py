from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from agent_trader.config import DEFAULT_CONFIG
from agent_trader.data.csv_loader import load_ohlcv_csv
from agent_trader.execution.signal_writer import make_signal, write_signal_csv
from agent_trader.features.builder import build_feature_rows
from agent_trader.ml.model import load_model, predict_proba
from agent_trader.policy.quality import decide_quality
from agent_trader.strategy.generator import CandidateInputs, generate_candidates


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h4", required=True)
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m15", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-prob", type=float, default=0.60)
    ap.add_argument("--mode", default="paper")
    args = ap.parse_args()

    cfg = DEFAULT_CONFIG
    h4 = load_ohlcv_csv(args.h4, schema="generic")
    h1 = load_ohlcv_csv(args.h1, schema="generic")
    m15 = load_ohlcv_csv(args.m15, schema="generic")

    artifacts = load_model(args.model)

    candidates = generate_candidates(CandidateInputs(h4=h4, h1=h1, m15=m15), cfg=cfg, live_gate=True)
    feat_rows = build_feature_rows(cfg=cfg, h4=h4, h1=h1, m15=m15, candidates=candidates)
    feat_df = pd.DataFrame([r.features for r in feat_rows])
    if len(feat_df) == 0:
        return 0
    probs = predict_proba(artifacts, feat_df)

    ranked = sorted(zip(candidates, probs), key=lambda x: x[1], reverse=True)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for cand, p in ranked:
        if p < args.min_prob:
            continue
        regime = str(cand.meta.get("market_regime") or "TRANSITION")
        session_state = str(cand.meta.get("session_state") or "BLOCKED")
        decision = decide_quality(
            probability=float(p),
            confluence_score=float(cand.confluence_score),
            market_regime=regime,  # type: ignore[arg-type]
            session_state=session_state,  # type: ignore[arg-type]
        )
        if decision.risk_multiplier <= 0.0 or decision.quality == "SKIP":
            continue
        sig = make_signal(
            symbol=cand.symbol,
            side=cand.side.value,
            entry=cand.entry_price,
            sl=cand.sl_price,
            tp=cand.tp_price,
            confluence=cand.confluence_score,
            model_probability=float(p),
            session_state=session_state,
            market_regime=regime,
            quality=decision.quality,
            risk_multiplier=decision.risk_multiplier,
            mode=args.mode,
            when=cand.time,
        )
        write_signal_csv(sig, out_dir=out_dir)
        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
