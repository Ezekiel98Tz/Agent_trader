from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import brier_score_loss, classification_report, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


@dataclass(frozen=True)
class ModelArtifacts:
    raw_pipeline: Pipeline
    calibrated_model: CalibratedClassifierCV | None
    calibration_method: str
    feature_columns: list[str]
    target_positive: str


def _make_pipeline(cat_cols: list[str], num_cols: list[str]) -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
            ("num", "passthrough", num_cols),
        ],
        remainder="drop",
    )
    clf = RandomForestClassifier(
        n_estimators=500,
        max_depth=6,
        min_samples_leaf=10,
        random_state=42,
        class_weight="balanced_subsample",
        n_jobs=-1,
    )
    return Pipeline([("pre", pre), ("clf", clf)])


def train_probability_model(
    df: pd.DataFrame,
    *,
    target_col: str = "label",
    positive_label: str = "win",
    drop_labels: Iterable[str] = ("breakeven",),
    calibration: str = "sigmoid",
    calibration_fraction: float = 0.2,
) -> tuple[ModelArtifacts, dict]:
    work = df.copy()
    work = work[~work[target_col].isin(drop_labels)].reset_index(drop=True)
    y = (work[target_col] == positive_label).astype(int)
    X = work.drop(columns=[target_col])

    cat_cols = [c for c in X.columns if X[c].dtype == "object"]
    num_cols = [c for c in X.columns if c not in cat_cols]
    raw_pipe = _make_pipeline(cat_cols, num_cols)

    tscv = TimeSeriesSplit(n_splits=5)
    oof = np.zeros(len(X), dtype=float)
    for train_idx, test_idx in tscv.split(X):
        pipe_fold = _make_pipeline(cat_cols, num_cols)
        pipe_fold.fit(X.iloc[train_idx], y.iloc[train_idx])
        oof[test_idx] = pipe_fold.predict_proba(X.iloc[test_idx])[:, 1]

    metrics = {
        "roc_auc_oof": float(roc_auc_score(y, oof)) if len(np.unique(y)) > 1 else float("nan"),
        "brier_oof": float(brier_score_loss(y, oof)),
        "report_oof": classification_report(y, (oof >= 0.5).astype(int), output_dict=True),
    }

    n = len(X)
    calib_n = int(max(0, min(n, round(n * calibration_fraction))))
    train_n = n - calib_n

    raw_pipe_full = _make_pipeline(cat_cols, num_cols)
    raw_pipe_full.fit(X, y)

    if calib_n >= 50 and train_n >= 200 and calibration in ("sigmoid", "isotonic"):
        X_train = X.iloc[:train_n]
        y_train = y.iloc[:train_n]
        X_cal = X.iloc[train_n:]
        y_cal = y.iloc[train_n:]
        raw_pipe_train = _make_pipeline(cat_cols, num_cols)
        raw_pipe_train.fit(X_train, y_train)
        cal = CalibratedClassifierCV(raw_pipe_train, method=calibration, cv="prefit")
        cal.fit(X_cal, y_cal)
        p_raw = raw_pipe_train.predict_proba(X_cal)[:, 1]
        p_cal = cal.predict_proba(X_cal)[:, 1]
        metrics.update(
            {
                "calibration_method": calibration,
                "brier_calibration_raw": float(brier_score_loss(y_cal, p_raw)),
                "brier_calibration_calibrated": float(brier_score_loss(y_cal, p_cal)),
                "calibration_samples": int(calib_n),
            }
        )
        calibrated_model: CalibratedClassifierCV | None = cal
        final_method = calibration
    else:
        calibrated_model = None
        final_method = "none"
        metrics.update({"calibration_method": "none", "calibration_samples": int(calib_n)})

    artifacts = ModelArtifacts(
        raw_pipeline=raw_pipe_full,
        calibrated_model=calibrated_model,
        calibration_method=final_method,
        feature_columns=list(X.columns),
        target_positive=positive_label,
    )
    return artifacts, metrics


def predict_proba_raw(artifacts: ModelArtifacts, df_features: pd.DataFrame) -> np.ndarray:
    X = df_features[artifacts.feature_columns]
    return artifacts.raw_pipeline.predict_proba(X)[:, 1]


def predict_proba(artifacts: ModelArtifacts, df_features: pd.DataFrame) -> np.ndarray:
    X = df_features[artifacts.feature_columns]
    if artifacts.calibrated_model is None:
        return artifacts.raw_pipeline.predict_proba(X)[:, 1]
    return artifacts.calibrated_model.predict_proba(X)[:, 1]


def save_model(artifacts: ModelArtifacts, path: str) -> None:
    joblib.dump(artifacts, path)


def load_model(path: str) -> ModelArtifacts:
    return joblib.load(path)


def feature_importances(artifacts: ModelArtifacts, top_n: int = 25) -> list[tuple[str, float]]:
    pre: ColumnTransformer = artifacts.raw_pipeline.named_steps["pre"]
    clf: RandomForestClassifier = artifacts.raw_pipeline.named_steps["clf"]

    cat: OneHotEncoder = pre.named_transformers_["cat"]
    cat_cols = pre.transformers_[0][2]
    num_cols = pre.transformers_[1][2]

    cat_names: list[str] = []
    if len(cat_cols):
        cat_names = list(cat.get_feature_names_out(cat_cols))
    feature_names = cat_names + list(num_cols)
    importances = clf.feature_importances_
    pairs = list(zip(feature_names, importances))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return [(n, float(v)) for n, v in pairs[:top_n]]
