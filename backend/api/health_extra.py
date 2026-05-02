"""Readiness checks for laptop one-command startup (optional browser / CI)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import text

from config import settings
from database import engine

router = APIRouter()

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_FRONTEND_DIR = _BACKEND_DIR.parent / "frontend"


@router.get("/ready")
def health_ready():
    checks: dict = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:  # noqa: BLE001
        checks["database"] = False
        checks["database_error"] = str(exc)

    try:
        import joblib as _jl

        checks["joblib"] = True
        checks["joblib_version"] = getattr(_jl, "__version__", "unknown")
    except Exception as exc:  # noqa: BLE001
        checks["joblib"] = False
        checks["joblib_error"] = str(exc)

    try:
        import sklearn

        checks["sklearn"] = True
        checks["sklearn_version"] = sklearn.__version__
    except Exception as exc:  # noqa: BLE001
        checks["sklearn"] = False
        checks["sklearn_error"] = str(exc)

    model_rel = Path(settings.ML_CLASSIFIER_MODEL_PATH)
    model_path = model_rel if model_rel.is_absolute() else _BACKEND_DIR / model_rel
    checks["ml_classifier_enabled"] = settings.ML_ANOM_CLASSIFIER_ENABLED
    checks["ml_model_path"] = str(model_path.resolve())
    checks["ml_model_file"] = model_path.is_file()

    bundle_ok = False
    if checks.get("joblib") and checks.get("sklearn") and checks["ml_model_file"] and settings.ML_ANOM_CLASSIFIER_ENABLED:
        try:
            from services.ml_classifier_service import load_classifier_bundle

            bundle_ok = load_classifier_bundle() is not None
        except Exception as exc:  # noqa: BLE001
            checks["ml_bundle_error"] = str(exc)
    checks["ml_bundle_loadable"] = bundle_ok

    checks["frontend_index"] = _FRONTEND_DIR.is_dir() and (_FRONTEND_DIR / "index.html").is_file()

    core = checks.get("database") and checks.get("joblib") and checks.get("sklearn")
    ml_required = settings.ML_ANOM_CLASSIFIER_ENABLED
    ml_ok = (not ml_required) or (checks.get("ml_model_file") and checks.get("ml_bundle_loadable"))
    checks["overall_ok"] = bool(core and ml_ok and checks.get("frontend_index"))

    return checks
