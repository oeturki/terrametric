# Dummy stream scenarios

Synthetic telemetry profiles shared by live dummy streaming (`StreamSupervisor`) and the Manage Samples **backfill** endpoint. Scenario keys match the backend `ScenarioName` literal in `backend/schemas/session_schema.py`.

## Live stream vs backfill

| Path | Detector pipeline |
|------|-------------------|
| **Live dummy stream** during an active recording | Each insert goes through `store_telemetry_row` → `run_detection_and_persist` when `plant_id` is set. |
| **Backfill** (bulk insert in one transaction) | Rows are written only; anomalies are **not** computed automatically. Run **`POST /api/anomalies/reprocess`** afterward to flag historical rows for a plant. |

**`packet_loss`** only creates timestamp gaps during **live streaming** (the supervisor skips bursts of inserts). Backfill emits one row per `interval_sec` with no deliberate gaps — use streaming to demo dropout.

## Cadence (~Arduino)

The HC-05 bridge forwards JSON lines emitted by the Arduino sketch roughly **every ~200 ms (~5 Hz)**; see `pi/arduino_bridge.py`. The Manage Samples dummy interval defaults to **`1 s`** and accepts **`0.2–300 s`** through the API so you can approximate **hardware cadence without waiting minutes per detector**. Sub-second ticks increase DB/anomaly workload — use **`1 s`** on weaker laptops unless you need a closer match.

Detectors fill rolling windows **per reading**, not purely by wall-clock time: **`stable` will rarely fire anything** — pick a labelled **FR10 demo** scenario (or **`heat_spike`**, **`cold_night`**, etc.). Expect roughly **≥ 6 stored readings before spike checks engage**, **≥ 30 for drift slope**, **≥ 10 for humidity/light noise**, and **≥ 35 normal inserts before `packet_loss` gap bursts appear** while dropout finishes its baseline.

## Scenario → FR10 detector emphasis

These map to core detectors enabled when `FR10_EXTENDED_DETECTORS` is left at default `false`.

| Scenario | What it does | Good for |
|----------|----------------|----------|
| `stable` | Healthy diurnal curves | Baseline (usually no anomalies) |
| `heat_spike` | Sharp +°C excursions on scattered ticks vs steady neighbour readings | Spike (temp) |
| `drought` | Humidity ramps down | Threshold / gradual stress |
| `cold_night` | Cooler temps when dark | Threshold / contextual |
| `sensor_drift` | Linear creep additive per reading (~0.06 °C/step) | Drift (temp) |
| `temp_spike_random` | Random-ish large positive spikes | Spike (temp) |
| `light_spike_burst` | Periodic + random sharp light outliers per **stored row** (not wall-clock only) vs diurnal baseline | Spike (light) |
| `humidity_noise_storm` | High-variance RH around nominal | Noise (humidity) |
| `drift_ramp_fast` | Steeper additive ramp per reading | Drift (temp) |
| `missing_temp_readings` | Intermittent `temperature=None`; other channels present | Missing channel |
| `packet_loss` | Skips bursts of inserts (after warmup) → large timestamp gaps vs learned interval | Dropout / gap |

Implementation details live in `backend/services/dummy_stream.py`.
