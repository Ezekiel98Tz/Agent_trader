from __future__ import annotations

import argparse
import json
import logging
import os
import time as time_mod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agent_trader.config import DEFAULT_CONFIG
from agent_trader.data.csv_loader import load_ohlcv_csv
from agent_trader.data.mt5_loader import get_spread_pips, load_recent_multi_timeframe
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
    signals_today: int
    spread_pips: float | None
    last_error: str | None


def _write_status(path: Path, status: ServiceStatus) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(status), separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)


def _day_key_utc(now: datetime) -> str:
    dt = now
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def _read_state(path: Path, now: datetime) -> dict:
    day = _day_key_utc(now)
    if not path.exists():
        return {"day": day, "signals_today": 0}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if raw.get("day") != day:
        return {"day": day, "signals_today": 0}
    if "signals_today" not in raw:
        raw["signals_today"] = 0
    return raw


def _write_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _pip_size(symbol: str) -> float:
    s = symbol.upper()
    return 0.01 if s.endswith("JPY") else 0.0001


def run_once(
    *,
    source: str,
    h4_path: str,
    h1_path: str,
    m15_path: str,
    mt5_symbol: str,
    bars_m15: int,
    bars_h1: int,
    bars_h4: int,
    model_path: str,
    out_dir: str,
    min_prob: float,
    mode: str,
    state_file: str,
    max_signals_per_day: int,
    max_spread_pips: float,
) -> ServiceStatus:
    cfg = DEFAULT_CONFIG
    now = datetime.now(timezone.utc)
    state_path = Path(state_file)
    state = _read_state(state_path, now)
    signals_today = int(state.get("signals_today", 0))
    if signals_today >= int(max_signals_per_day):
        return ServiceStatus(
            time_utc=now.isoformat(),
            session_state="BLOCKED",
            candidates=0,
            wrote_signal=False,
            last_signal_id=None,
            signals_today=signals_today,
            spread_pips=None,
            last_error="max_signals_per_day_reached",
        )

    spread_pips: float | None = None
    if source == "mt5":
        frames = load_recent_multi_timeframe(
            symbol=str(mt5_symbol),
            bars_by_tf={"M15": int(bars_m15), "H1": int(bars_h1), "H4": int(bars_h4)},
            timezone="UTC",
        )
        m15 = frames["M15"]
        h1 = frames["H1"]
        h4 = frames["H4"]
        spread_pips = get_spread_pips(symbol=str(mt5_symbol), pip_size=_pip_size(str(mt5_symbol)))
        if spread_pips is not None and float(spread_pips) > float(max_spread_pips):
            return ServiceStatus(
                time_utc=now.isoformat(),
                session_state="BLOCKED",
                candidates=0,
                wrote_signal=False,
                last_signal_id=None,
                signals_today=signals_today,
                spread_pips=float(spread_pips),
                last_error="spread_too_high",
            )
    else:
        h4 = load_ohlcv_csv(h4_path, schema="generic")
        h1 = load_ohlcv_csv(h1_path, schema="generic")
        m15 = load_ohlcv_csv(m15_path, schema="generic")

    latest_t = pd.to_datetime(m15["time"].iloc[-1]).to_pydatetime()
    ss = get_session_state(latest_t)
    now_iso = now.isoformat()

    if ss == "BLOCKED":
        return ServiceStatus(
            time_utc=now_iso,
            session_state=ss,
            candidates=0,
            wrote_signal=False,
            last_signal_id=None,
            signals_today=signals_today,
            spread_pips=spread_pips,
            last_error=None,
        )

    artifacts = load_model(model_path)
    candidates = generate_candidates(CandidateInputs(h4=h4, h1=h1, m15=m15), cfg=cfg, live_gate=True)
    if not candidates:
        return ServiceStatus(
            time_utc=now_iso,
            session_state=ss,
            candidates=0,
            wrote_signal=False,
            last_signal_id=None,
            signals_today=signals_today,
            spread_pips=spread_pips,
            last_error=None,
        )

    feat_rows = build_feature_rows(cfg=cfg, h4=h4, h1=h1, m15=m15, candidates=candidates)
    feat_df = pd.DataFrame([r.features for r in feat_rows])
    if len(feat_df) == 0:
        return ServiceStatus(
            time_utc=now_iso,
            session_state=ss,
            candidates=0,
            wrote_signal=False,
            last_signal_id=None,
            signals_today=signals_today,
            spread_pips=spread_pips,
            last_error=None,
        )

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
        state["signals_today"] = int(signals_today) + 1
        _write_state(state_path, state)
        return ServiceStatus(
            time_utc=now_iso,
            session_state=ss,
            candidates=len(candidates),
            wrote_signal=True,
            last_signal_id=sig.id,
            signals_today=int(state["signals_today"]),
            spread_pips=spread_pips,
            last_error=None,
        )

    return ServiceStatus(
        time_utc=now_iso,
        session_state=ss,
        candidates=len(candidates),
        wrote_signal=False,
        last_signal_id=None,
        signals_today=signals_today,
        spread_pips=spread_pips,
        last_error=None,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["csv", "mt5"], default="csv")
    ap.add_argument("--h4", default="")
    ap.add_argument("--h1", default="")
    ap.add_argument("--m15", default="")
    ap.add_argument("--symbol", default=DEFAULT_CONFIG.symbol)
    ap.add_argument("--bars-m15", type=int, default=1500)
    ap.add_argument("--bars-h1", type=int, default=800)
    ap.add_argument("--bars-h4", type=int, default=500)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-prob", type=float, default=0.60)
    ap.add_argument("--mode", default="paper")
    ap.add_argument("--interval-seconds", type=int, default=60)
    ap.add_argument("--status-file", default="service_status.json")
    ap.add_argument("--state-file", default="service_state.json")
    ap.add_argument("--max-signals-per-day", type=int, default=DEFAULT_CONFIG.max_signals_per_day)
    ap.add_argument("--max-spread-pips", type=float, default=DEFAULT_CONFIG.max_spread_pips)
    ap.add_argument("--log-file", default="")
    args = ap.parse_args()

    log_level = os.environ.get("AGENT_TRADER_LOG_LEVEL", "INFO").upper()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), handlers=handlers, format="%(asctime)s %(levelname)s %(message)s")

    status_path = Path(args.status_file)
    while True:
        try:
            if args.source == "csv" and (not args.h4 or not args.h1 or not args.m15):
                raise ValueError("--h4/--h1/--m15 are required when --source=csv")

            s = run_once(
                source=str(args.source),
                h4_path=str(args.h4),
                h1_path=str(args.h1),
                m15_path=str(args.m15),
                mt5_symbol=str(args.symbol),
                bars_m15=int(args.bars_m15),
                bars_h1=int(args.bars_h1),
                bars_h4=int(args.bars_h4),
                model_path=str(args.model),
                out_dir=str(args.out_dir),
                min_prob=float(args.min_prob),
                mode=str(args.mode),
                state_file=str(args.state_file),
                max_signals_per_day=int(args.max_signals_per_day),
                max_spread_pips=float(args.max_spread_pips),
            )
        except Exception as e:  # noqa: BLE001
            now_iso = datetime.now(timezone.utc).isoformat()
            logging.exception("service_run_error")
            s = ServiceStatus(
                time_utc=now_iso,
                session_state="BLOCKED",
                candidates=0,
                wrote_signal=False,
                last_signal_id=None,
                signals_today=0,
                spread_pips=None,
                last_error=str(e),
            )

        _write_status(status_path, s)
        time_mod.sleep(max(1, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
