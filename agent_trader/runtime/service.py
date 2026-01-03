from __future__ import annotations

import argparse
import json
import time as time_mod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agent_trader.config import DEFAULT_CONFIG
from agent_trader.data.csv_loader import load_ohlcv_csv
from agent_trader.execution.signal_writer import make_signal, write_signal_csv
from agent_trader.features.builder import build_feature_rows
from agent_trader.ml.model import load_model, predict_proba
from agent_trader.policy.quality import decide_quality
from agent_trader.session.session_filter import get_session_state
from agent_trader.strategy.generator import CandidateInputs, generate_candidates


@dataclass(frozen=True)
class ServiceStatus:
    time_utc: str
    session_state: str
    candidates: int
    wrote_signal: bool
    last_signal_id: str | None


def _write_status(path: Path, status: ServiceStatus) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(status), separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)


def run_once(
    *,
    h4_path: str,
    h1_path: str,
    m15_path: str,
    model_path: str,
    out_dir: str,
    min_prob: float,
    mode: str,
) -> ServiceStatus:
    cfg = DEFAULT_CONFIG
    h4 = load_ohlcv_csv(h4_path, schema="generic")
    h1 = load_ohlcv_csv(h1_path, schema="generic")
    m15 = load_ohlcv_csv(m15_path, schema="generic")

    latest_t = pd.to_datetime(m15["time"].iloc[-1]).to_pydatetime()
    ss = get_session_state(latest_t)
    now_iso = datetime.now(timezone.utc).isoformat()

    if ss == "BLOCKED":
        return ServiceStatus(time_utc=now_iso, session_state=ss, candidates=0, wrote_signal=False, last_signal_id=None)

    artifacts = load_model(model_path)
    candidates = generate_candidates(CandidateInputs(h4=h4, h1=h1, m15=m15), cfg=cfg, live_gate=True)
    if not candidates:
        return ServiceStatus(time_utc=now_iso, session_state=ss, candidates=0, wrote_signal=False, last_signal_id=None)

    feat_rows = build_feature_rows(cfg=cfg, h4=h4, h1=h1, m15=m15, candidates=candidates)
    feat_df = pd.DataFrame([r.features for r in feat_rows])
    if len(feat_df) == 0:
        return ServiceStatus(time_utc=now_iso, session_state=ss, candidates=0, wrote_signal=False, last_signal_id=None)

    probs = predict_proba(artifacts, feat_df)
    ranked = sorted(zip(candidates, probs), key=lambda x: x[1], reverse=True)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    for cand, p in ranked:
        if float(p) < float(min_prob):
            continue
        regime = str(cand.meta.get("market_regime") or "TRANSITION")
        session_state = str(cand.meta.get("session_state") or "BLOCKED")
        decision = decide_quality(
            probability=float(p),
            confluence_score=float(cand.confluence_score),
            market_regime=regime,  # type: ignore[arg-type]
            session_state=session_state,  # type: ignore[arg-type]
        )
        if decision.quality == "SKIP" or decision.risk_multiplier <= 0.0:
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
            mode=mode,
            when=cand.time,
        )
        write_signal_csv(sig, out_dir=out_path)
        return ServiceStatus(time_utc=now_iso, session_state=ss, candidates=len(candidates), wrote_signal=True, last_signal_id=sig.id)

    return ServiceStatus(time_utc=now_iso, session_state=ss, candidates=len(candidates), wrote_signal=False, last_signal_id=None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h4", required=True)
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m15", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-prob", type=float, default=0.60)
    ap.add_argument("--mode", default="paper")
    ap.add_argument("--interval-seconds", type=int, default=60)
    ap.add_argument("--status-file", default="service_status.json")
    args = ap.parse_args()

    status_path = Path(args.status_file)
    while True:
        s = run_once(
            h4_path=args.h4,
            h1_path=args.h1,
            m15_path=args.m15,
            model_path=args.model,
            out_dir=args.out_dir,
            min_prob=float(args.min_prob),
            mode=str(args.mode),
        )
        _write_status(status_path, s)
        time_mod.sleep(max(1, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())

