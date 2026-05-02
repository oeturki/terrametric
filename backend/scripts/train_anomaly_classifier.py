#!/usr/bin/env python3
"""
Train sklearn anomaly-type classifier from weak_labels_dataset or bootstrap synthetic rows.

Produces joblib artifact for ``services.ml_classifier_service``:
  pipeline: SimpleImputer + LogisticRegression (class_weight=balanced)
  feature_names / feature_version / sklearn_version metadata

Examples:
  python scripts/train_anomaly_classifier.py --bootstrap --out artifacts/anomaly_classifier.joblib
  python scripts/train_anomaly_classifier.py --dataset artifacts/weak_labels_dataset.parquet --out artifacts/anomaly_classifier.joblib
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from types import SimpleNamespace

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
import sklearn  # noqa: E402

from services.ml_telemetry_features import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_VERSION,
    telemetry_rows_to_matrix,
)


ALL_LABELS = [
    "normal",
    "spike",
    "drift",
    "noise",
    "dropout",
    "missing_data",
    "correlation",
    "level_shift",
    "ewma_breach",
    "seasonal",
    "other",
]


def dataframe_to_metric_rows(frame: pd.DataFrame) -> list[SimpleNamespace]:
    rows = []
    for _, r in frame.iterrows():
        rows.append(
            SimpleNamespace(
                id=int(r.telemetry_id) if pd.notna(r.telemetry_id) else None,
                plant_id=r.plant_id,
                timestamp=pd.Timestamp(r.timestamp).to_pydatetime() if pd.notna(r.timestamp) else None,
                temperature=r.temperature,
                humidity=r.humidity,
                light=r.light,
                movement=r.movement,
                distance=r.distance,
                plant_height=r.plant_height,
            )
        )
    return rows


def stack_features_from_dataset(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    df = df.sort_values(["timestamp", "telemetry_id"])
    for _, g in df.groupby("plant_id", sort=False):
        g_sorted = g.sort_values(["timestamp", "telemetry_id"]).reset_index(drop=True)
        ns = dataframe_to_metric_rows(g_sorted)
        Xg = telemetry_rows_to_matrix(ns)
        yg = g_sorted["weak_label"].astype(str).values
        if len(ns) >= 2:
            X_parts.append(Xg)
            y_parts.append(yg)
    if not X_parts:
        return np.zeros((0, len(FEATURE_NAMES))), np.array([], dtype=object)
    return np.vstack(X_parts), np.concatenate(y_parts)


def make_bootstrap_xy(n_samples: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = rng.normal(scale=3.5, size=(n_samples, len(FEATURE_NAMES)))
    y_int = rng.integers(0, len(ALL_LABELS), size=n_samples)
    y = np.array([ALL_LABELS[i] for i in y_int], dtype=object)
    noise = rng.normal(scale=[1.8, 1.8, 2.8, 0.6, 2.8, 0.8, 0.8, 0.88, 0.8, 0.8, 0.62, 0.62, 1.02, 0.68], size=X.shape)
    X = X + noise * rng.normal(size=X.shape) * 0.15

    anomaly_idx = rng.choice(n_samples, max(1, n_samples // 4), replace=False)
    anomaly_pick = rng.choice([t for t in ALL_LABELS if t != "normal"], size=len(anomaly_idx))
    for ii, j in enumerate(anomaly_idx):
        X[j, min(ii % len(FEATURE_NAMES), len(FEATURE_NAMES) - 1)] *= rng.choice([2.2, -2.1, 2.8])
        y[j] = anomaly_pick[ii]

    return X.astype(np.float64), y.astype(object)


def build_pipeline(X: np.ndarray, y: np.ndarray) -> Pipeline:
    if len(set(y.tolist())) < 2:
        raise SystemExit(
            "Need at least two classes in y. Build a larger weak-label window or pass --bootstrap."
        )

    preprocessor = ColumnTransformer(
        transformers=[("floats", SimpleImputer(strategy="median"), list(range(len(FEATURE_NAMES))))],
        remainder="drop",
    )

    clf = LogisticRegression(
        max_iter=800,
        class_weight="balanced",
        random_state=42,
        solver="lbfgs",
    )

    pipe = Pipeline([("pre", preprocessor), ("clf", clf)])
    pipe.fit(X, y)
    return pipe


def main() -> None:
    ap = argparse.ArgumentParser(description="Train anomaly classifier artifact")
    ap.add_argument("--dataset", default="", help="Path to weak_labels_dataset parquet/csv")
    ap.add_argument("--bootstrap", action="store_true", help="Ignore DB export; synthesize tabular data")
    ap.add_argument("--bootstrap-samples", type=int, default=900)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--out",
        default=os.path.join(_BACKEND_ROOT, "artifacts", "anomaly_classifier.joblib"),
        help="Output joblib bundle path",
    )
    args = ap.parse_args()

    if args.bootstrap:
        X, y = make_bootstrap_xy(args.bootstrap_samples, args.seed)
    else:
        if not args.dataset:
            sys.exit("--dataset required unless --bootstrap")
        df = pd.read_parquet(args.dataset) if args.dataset.endswith(".parquet") else pd.read_csv(args.dataset)
        if "weak_label" not in df.columns:
            sys.exit("Dataset missing weak_label column — run scripts/build_weak_labels_dataset.py")
        X, y = stack_features_from_dataset(df)
        if len(y) == 0:
            sys.exit("No usable rows — check telemetry has plant_id and multiple rows per plant.")

    bundle = {
        "pipeline": build_pipeline(X, y),
        "feature_names": list(FEATURE_NAMES),
        "feature_version": FEATURE_VERSION,
        "sklearn_version": sklearn.__version__,
        "class_labels_seen": sorted({str(z) for z in y.tolist()}),
    }

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    joblib.dump(bundle, out_path)

    manifest = os.path.join(os.path.dirname(out_path), "anomaly_classifier_manifest.json")
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(
            {"sklearn_version": bundle["sklearn_version"], "feature_version": FEATURE_VERSION, "artifact": bundle["class_labels_seen"]},
            f,
            indent=2,
        )

    print("saved", out_path)
    print("sklearn", bundle["sklearn_version"], "features", FEATURE_VERSION)


if __name__ == "__main__":
    main()
