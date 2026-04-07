"""
Simulation Engine  [Owner: Omer]
Generates synthetic telemetry data and feeds it into the same backend pipeline
as live sensor data, enabling deterministic validation without hardware.

Capabilities:
  - Generate stable readings within setpoints
  - Inject controlled deviations (spikes, drift, gaps)
  - Configurable duration, sampling rate, and noise level
"""


# TODO: generate_stable_series(duration_min, interval_sec, setpoints) -> list of readings
# TODO: inject_spike(series, timestamp, variable, magnitude) -> modified series
# TODO: inject_drift(series, start_time, end_time, variable, slope) -> modified series
# TODO: inject_gap(series, start_time, gap_duration) -> modified series with missing points
# TODO: run_simulation(config) -> feeds generated data through the processing pipeline
