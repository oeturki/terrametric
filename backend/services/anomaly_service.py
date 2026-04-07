"""
FR10 - Anomaly Detection Service  [Owner: Omer]
Detect anomalies beyond static thresholds:
  - Spikes: sudden jump beyond expected change rate
  - Drift: gradual bias over time (slope exceeds threshold)
  - Missing data: gaps > N consecutive samples

Test scenarios (synthetic datasets in simulation/datasets/):
  A) Spike: constant 22C, one point at 35C, back to 22C -> "Spike anomaly"
  B) Drift: 22C increasing +0.1C/min for 60 min -> "Drift anomaly" when slope > threshold
  C) Missing: 10 consecutive points removed -> "Missing data anomaly"

Acceptance:
  - Flag generated within one update cycle
  - Anomaly event in logs with timestamp + type
"""


# TODO: detect_spikes(readings, threshold) -> list of spike events
# TODO: detect_drift(readings, window_minutes, slope_threshold) -> list of drift events
# TODO: detect_missing_data(readings, gap_threshold) -> list of gap events
# TODO: run_anomaly_detection(session_id) -> all anomaly events for session
