from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from agent_trader.config import DEFAULT_CONFIG
from agent_trader.data.csv_loader import load_ohlcv_csv
from agent_trader.features.builder import build_feature_rows
from agent_trader.labeling.labeler import label_candidates
from agent_trader.ml.model import feature_importances, save_model, train_probability_model
from agent_trader.strategy.generator import CandidateInputs, generate_candidates


def _rows_to_frame(rows):
    df = pd.DataFrame([r.features for r in rows])
    df["time"] = [r.time for r in rows]
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h4", required=True)
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m15", required=True)
    ap.add_argument("--out-model", required=True)
    ap.add_argument("--out-dataset", required=False)
    ap.add_argument("--calibration", choices=["none", "sigmoid", "isotonic"], default="sigmoid")
    args = ap.parse_args()

    cfg = DEFAULT_CONFIG
    h4 = load_ohlcv_csv(args.h4, schema="generic")
    h1 = load_ohlcv_csv(args.h1, schema="generic")
    m15 = load_ohlcv_csv(args.m15, schema="generic")

    candidates = generate_candidates(CandidateInputs(h4=h4, h1=h1, m15=m15), cfg=cfg)
    feat_rows = build_feature_rows(cfg=cfg, h4=h4, h1=h1, m15=m15, candidates=candidates)
    feat_df = _rows_to_frame(feat_rows)

    label_res = label_candidates(cfg=cfg, m15=m15, candidates=candidates)
    label_df = pd.DataFrame(
        {
            "time": [lt.candidate.time for lt in label_res.labeled],
            "label": [lt.label for lt in label_res.labeled],
            "mfe_pips": [lt.mfe_pips for lt in label_res.labeled],
            "mae_pips": [lt.mae_pips for lt in label_res.labeled],
            "minutes_to_outcome": [lt.minutes_to_outcome for lt in label_res.labeled],
        }
    )

    dataset = feat_df.merge(label_df, on="time", how="inner")
    if args.out_dataset:
        Path(args.out_dataset).parent.mkdir(parents=True, exist_ok=True)
        dataset.to_csv(args.out_dataset, index=False)

    artifacts, metrics = train_probability_model(
        dataset.drop(columns=["time"]),
        target_col="label",
        calibration=("none" if args.calibration == "none" else args.calibration),
    )
    save_model(artifacts, args.out_model)

    top = feature_importances(artifacts, top_n=20)
    metrics_out = {
        **metrics,
        "feature_importances_top20": top,
        "candidates": len(candidates),
        "labeled": len(label_res.labeled),
        "dropped": label_res.dropped,
    }
    print(pd.Series(metrics_out).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
