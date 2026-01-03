from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent_trader.execution.signal_schema import TradeSignal


def write_signal_json(signal: TradeSignal, *, out_dir: str | Path) -> Path:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    payload = asdict(signal)
    payload["time_utc"] = signal.time_utc.astimezone(timezone.utc).isoformat()
    path = p / f"signal_{signal.id}.json"
    tmp = p / f".signal_{signal.id}.json.tmp"
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)
    return path


def write_signal_csv(signal: TradeSignal, *, out_dir: str | Path) -> Path:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    ts = signal.time_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = ",".join(
        [
            signal.id,
            ts,
            signal.symbol,
            signal.side,
            f"{signal.entry:.5f}",
            f"{signal.sl:.5f}",
            f"{signal.tp:.5f}",
            f"{signal.confluence:.6f}",
            f"{signal.model_probability:.6f}",
            signal.session_state,
            signal.market_regime,
            signal.quality,
            f"{signal.risk_multiplier:.4f}",
            signal.mode,
        ]
    )
    path = p / f"signal_{signal.id}.csv"
    tmp = p / f".signal_{signal.id}.csv.tmp"
    tmp.write_text(line)
    tmp.replace(path)
    return path


def make_signal(
    *,
    symbol: str,
    side: str,
    entry: float,
    sl: float,
    tp: float,
    confluence: float,
    model_probability: float,
    session_state: str,
    market_regime: str,
    quality: str,
    risk_multiplier: float,
    mode: str = "paper",
    when: datetime | None = None,
) -> TradeSignal:
    return TradeSignal(
        id=uuid4().hex,
        time_utc=(when or datetime.now(timezone.utc)),
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        entry=float(entry),
        sl=float(sl),
        tp=float(tp),
        confluence=float(confluence),
        model_probability=float(model_probability),
        session_state=session_state,  # type: ignore[arg-type]
        market_regime=market_regime,  # type: ignore[arg-type]
        quality=quality,  # type: ignore[arg-type]
        risk_multiplier=float(risk_multiplier),
        mode=mode,  # type: ignore[arg-type]
    )
