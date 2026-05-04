"""Load sklearn artifact; batch anomaly-type classification on stored telemetry windows."""

from __future__ import annotations

import logging
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger(__name__)

_bundle: Dict[str, Any] | None | bool = False  # False = not loaded yet; None = failed/missing


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def classifier_model_path() -> Path:
    p = Path(settings.ML_CLASSIFIER_MODEL_PATH)
    if not p.is_absolute():
        return _backend_dir() / p
    return p


def load_classifier_bundle() -> Dict[str, Any] | None:
    """Return persisted dict with pipeline, feature_names, feature_version / sklearn_version, or None."""
    global _bundle
    if _bundle not in (False,):
        return _bundle if isinstance(_bundle, dict) else None
    if not settings.ML_ANOM_CLASSIFIER_ENABLED:
        return None
    path = classifier_model_path()
    if not path.is_file():
        logger.warning("ML classifier artifact missing at %s", path)
        _bundle = None
        return None
    try:
        _bundle = joblib.load(path)
        if not isinstance(_bundle, dict) or "pipeline" not in _bundle:
            logger.error("Classifier artifact malformed (expected dict with pipeline key)")
            _bundle = None
            return None
        return _bundle
    except Exception:
        logger.exception("Failed loading ML classifier artifact")
        _bundle = None
        return None


def predictor_ready() -> bool:
    return load_classifier_bundle() is not None


# sklearn artifact often predicts "seasonal" for daylight diurnal+sudden outliers.
# Bump obvious single-step outliers to spike using the same intuition as SpikeDetector z vs trailing std.

_SPIKE_HINT_Z = 4.0
_HINT_CHAN = (
    ("d_temp", "roll_std_temp", 0.5, 2.5),
    ("d_hum", "roll_std_hum", 2.0, 7.0),
    ("d_light", "roll_std_light", 20.0, 65.0),
)


def _scale_with_floor(roll_std_val: Any, baseline_noise: float) -> float:
    floor = max(baseline_noise / 4.0, 1e-9)
    try:
        rs = float(roll_std_val)
        if math.isfinite(rs) and rs > 0:
            return max(rs, floor)
    except (TypeError, ValueError):
        pass
    return floor


def ml_row_signals_instantaneous_spike(feature_map: Dict[str, float]) -> bool:
    """True when any channel jumps vs trailing-window scale similarly to SpikeDetector WARNING gate."""

    for d_key, rs_key, baseline, abs_min in _HINT_CHAN:
        try:
            d = float(feature_map[d_key])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(d) or abs(d) < abs_min:
            continue
        scale = _scale_with_floor(feature_map.get(rs_key), baseline)
        if abs(d) / scale >= _SPIKE_HINT_Z:
            return True
    return False


def _apply_spike_overrides_ml(labels: List[str], X: np.ndarray, feature_names: tuple[str, ...]) -> List[str]:
    out: List[str] = []
    for i, pred in enumerate(labels):
        if pred == "spike":
            out.append("spike")
            continue
        m: Dict[str, float] = {}
        try:
            for j, name in enumerate(feature_names):
                v = float(X[i, j])
                m[name] = v if math.isfinite(v) else math.nan
        except Exception:
            out.append(pred)
            continue
        if ml_row_signals_instantaneous_spike(m):
            out.append("spike")
        else:
            out.append(pred)
    return out


def classify_telemetry_sequence(rows: List[Any]) -> tuple[list[str], Dict[str, int]]:
    """
    Rows sorted ascending by timestamp for one plant.

    After sklearn predicts each row, a lightweight spike refinement runs: abrupt single-step jumps
    (vs trailing-window std floor, similar to SpikeDetector) relabel burst rows—especially useful when
    the tree model votes *seasonal* on diurnal traces with injected light spikes.

    Returns (per_row labels, aggregate Counter dict).
    """
    bundle = load_classifier_bundle()
    if not bundle or not rows:
        return [], {}
    pipe = bundle["pipeline"]
    from services.ml_telemetry_features import FEATURE_NAMES, telemetry_rows_to_matrix

    X = telemetry_rows_to_matrix(rows)
    yhat = pipe.predict(X)
    labels = _apply_spike_overrides_ml([str(c) for c in yhat], X, FEATURE_NAMES)
    counts = dict(Counter(labels))
    return labels, counts


def _persist_rows(
    db: Session,
    *,
    plant_id: int,
    rows: List[Any],
    labels: List[str],
    feature_version: str,
) -> None:
    if not labels:
        return
    from models.telemetry_ml_prediction import TelemetryMlPrediction

    for row, lab in zip(rows, labels):
        tid = getattr(row, "id", None)
        if tid is None:
            continue
        existing = db.query(TelemetryMlPrediction).filter(TelemetryMlPrediction.telemetry_id == tid).first()
        if existing:
            existing.predicted_class = lab
            existing.feature_version = feature_version
            existing.plant_id = plant_id
        else:
            db.add(
                TelemetryMlPrediction(
                    plant_id=plant_id,
                    telemetry_id=int(tid),
                    predicted_class=lab,
                    feature_version=feature_version,
                )
            )
    db.commit()


def classify_plant_window(
    db: Session,
    *,
    plant_id: int,
    hours: int,
    persist: bool,
) -> Dict[str, Any]:
    from datetime import datetime, timedelta

    from services.ml_telemetry_features import FEATURE_VERSION
    from services.telemetry_service import query_telemetry_for_plant_since

    bundle = load_classifier_bundle()
    if not settings.ML_ANOM_CLASSIFIER_ENABLED:
        return {
            "ml_enabled": False,
            "counts": {},
            "rows_scored": 0,
            "detail": "disabled",
            "message": "ML classifier disabled (ML_ANOM_CLASSIFIER_ENABLED=false or missing from env). Ship artifacts/anomaly_classifier.joblib or re-enable in backend/.env.",
            "feature_version": FEATURE_VERSION,
        }
    if bundle is None:
        return {
            "ml_enabled": True,
            "counts": {},
            "rows_scored": 0,
            "detail": "no_model_file",
            "message": f"No model found at {classifier_model_path()}",
            "feature_version": FEATURE_VERSION,
        }

    fv = bundle.get("feature_version", FEATURE_VERSION)
    sk_ver = bundle.get("sklearn_version", "")

    cutoff = datetime.utcnow() - timedelta(hours=max(1, min(int(hours), 720)))
    rows = query_telemetry_for_plant_since(db, plant_id=plant_id, since=cutoff).all()
    labels, counts = classify_telemetry_sequence(rows)
    counts = counts or {}

    ALL = [
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
    for k in ALL:
        counts.setdefault(k, 0)

    if persist and rows and labels:
        try:
            _persist_rows(db, plant_id=plant_id, rows=rows, labels=labels, feature_version=str(fv))
        except Exception:
            logger.exception("persist_ml_predictions_failed plant_id=%s", plant_id)
            db.rollback()

    return {
        "ml_enabled": True,
        "counts": counts,
        "rows_scored": len(rows),
        "sklearn_version": sk_ver,
        "feature_version": fv,
        "model_path": str(classifier_model_path()),
    }

