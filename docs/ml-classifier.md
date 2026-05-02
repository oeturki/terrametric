# ML anomaly classifier (MVP)

Server-side **multiclass** sketch over tabular telemetry features. It is **not** a replacement for the rule engine: training uses **weak labels** derived from persisted `anomaly_detection_events` (and temporal proximity), so the model inherits the same blind spots as the detectors.

## Design choice: stored telemetry only

**Realtime Arduino ingest** should stay on the **rule detectors** (fast, explainable, bounded cost). The ML pass is meant to **analyse history already in the database** for a sample (`plant_id`): you run a **window scan** (UI *Run ML scan* or `POST /api/ml/classify/window`). That gives one predicted label **per telemetry row** in that window. Optional `persist: true` saves results to `telemetry_ml_predictions` for reporting—there is **no** automatic ML step on every incoming reading.

## Inference (shipped with the repo)

1. Install backend deps (`scikit-learn`, `joblib`, … in `requirements.txt`).

2. Default artifact: `backend/artifacts/anomaly_classifier.joblib` (`ML_CLASSIFIER_MODEL_PATH`).

3. **`ML_ANOM_CLASSIFIER_ENABLED`** defaults to **`true`** in `config.py`. Override in `backend/.env` only if you need to disable ML on a very weak host (`false`).

4. **Batch scan** — `POST /api/ml/classify/window` body `{ "plant_id": n, "hours": 24, "persist": false }`. Set **`persist": true`** to upsert one row per telemetry row into `telemetry_ml_predictions`.

## Artifact contents

Training writes a joblib dict:

- `pipeline` — sklearn `Pipeline` (`SimpleImputer` + `LogisticRegression` by default in the training script — swap in e.g. RandomForest in the script if you need a heavier model), `predict` expects shape `(n, len(FEATURE_NAMES))`
- `feature_names`, `feature_version` (`services.ml_telemetry_features.FEATURE_VERSION`)
- `sklearn_version` — version used at train time (loading should use the **same minor** sklearn when possible).

A small `anomaly_classifier_manifest.json` sits next to the joblib summarising versions.

## Weak labels (`scripts/build_weak_labels_dataset.py`)

- Joins anomalies to telemetry by `telemetry_id`, and assigns labels within **±120 s** of an event anchor (`telemetry.timestamp` when linked, otherwise `created_at`).
- **`normal`** if no anomaly hit that row after the merges.
- **Multi-type merges** use deterministic priority:

  `spike` → `level_shift` → `ewma_breach` → `dropout`/`missing_data` → `drift` → `noise` → `correlation` → `seasonal`.

Outputs `artifacts/weak_labels_dataset.parquet` (CSV with `--out ...csv`).

## Training (`scripts/train_anomaly_classifier.py`)

From `backend/`:

```bash
python scripts/build_weak_labels_dataset.py --hours 720 --out artifacts/weak_labels_dataset.parquet
python scripts/train_anomaly_classifier.py --dataset artifacts/weak_labels_dataset.parquet --out artifacts/anomaly_classifier.joblib
```

**Bootstrap demo** (no DB history required):

```bash
python scripts/train_anomaly_classifier.py --bootstrap --out artifacts/anomaly_classifier.joblib
```

## Evaluation habit (coursework)

Split by **held-out time range**, not IID row sampling, when you report metrics — rows in the same plant stream are correlated.

## Synthetic HTTP lab

`POST /api/anomalies/simulate` and `DELETE /api/anomalies/clear` are **off** by default (`ALLOW_ANOMALY_SIMULATE=false`). The static TerraMetric UI no longer calls them; enable only for API-only demos or tests.
