"""
Simulation pipeline validation tests.  [Owner: Omer]

End-to-end tests that generate synthetic data via the simulator,
feed it through the anomaly detection service, and verify correct
detection against known ground-truth scenarios.

Run with: pytest tests/test_simulation.py -v
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.anomaly_service import AnomalyDetectionService
from services.detectors.base import AnomalyEvent, Reading
from simulation.simulator import (
    generate_stable_series,
    inject_drift,
    inject_noise,
    inject_gap,
)
from enums import AnomalyType


def _reading_from_dict(d, session_id=1):
    """Convert a simulator dict into a Reading dataclass."""
    return Reading(
        session_id=session_id,
        timestamp=datetime.fromisoformat(d["timestamp"]),
        temperature=d.get("temperature"),
        humidity=d.get("humidity"),
        light=d.get("light"),
        movement=d.get("movement"),
        distance=d.get("distance"),
    )


class TestSimulatorFunctions:

    def test_stable_series_length(self):
        series = generate_stable_series(duration_min=10, interval_sec=60)
        assert len(series) == 10

    def test_stable_series_has_all_fields(self):
        series = generate_stable_series(duration_min=1, interval_sec=60)
        r = series[0]
        assert "timestamp" in r
        assert "temperature" in r
        assert "humidity" in r
        assert "light" in r

    def test_inject_drift_changes_values(self):
        series = generate_stable_series(duration_min=10, interval_sec=60, seed=1)
        original_last = series[-1]["temperature"]
        series = inject_drift(series, "temperature", slope_per_reading=1.0)
        assert series[-1]["temperature"] > original_last + 5

    def test_inject_noise_increases_variance(self):
        import numpy as np

        stable = generate_stable_series(duration_min=30, interval_sec=60, seed=2)
        stable_temps = [r["temperature"] for r in stable]
        stable_std = np.std(stable_temps)

        noisy = generate_stable_series(duration_min=30, interval_sec=60, seed=2)
        noisy = inject_noise(noisy, "temperature", noise_std=5.0, seed=3)
        noisy_temps = [r["temperature"] for r in noisy]
        noisy_std = np.std(noisy_temps)

        assert noisy_std > stable_std * 2

    def test_inject_gap_removes_readings(self):
        series = generate_stable_series(duration_min=20, interval_sec=60)
        original_len = len(series)
        series = inject_gap(series, start_index=5, gap_count=5)
        assert len(series) == original_len - 5


class TestEndToEndStable:
    """Stable data should produce zero anomalies."""

    def test_no_anomalies_on_stable_data(self):
        service = AnomalyDetectionService(
            drift_window=10, noise_window=10,
            dropout_multiplier=3, dropout_baseline_count=5,
        )
        series = generate_stable_series(duration_min=30, interval_sec=60, seed=42)

        all_events = []
        for d in series:
            reading = _reading_from_dict(d)
            all_events.extend(service.process_reading(reading))

        # Stable data should not produce drift or dropout events
        drift_events = [e for e in all_events if e.anomaly_type == AnomalyType.DRIFT]
        dropout_events = [e for e in all_events if e.anomaly_type == AnomalyType.DROPOUT]
        assert len(drift_events) == 0
        assert len(dropout_events) == 0


class TestEndToEndDrift:
    """Drifting temperature should be detected."""

    def test_drift_detected_in_simulated_data(self):
        service = AnomalyDetectionService(
            drift_window=10, noise_window=10,
            dropout_multiplier=3, dropout_baseline_count=5,
        )
        series = generate_stable_series(
            duration_min=30, interval_sec=60, seed=50,
            noise_std={"temperature": 0.05, "humidity": 0.05, "light": 1.0},
        )
        series = inject_drift(series, "temperature", slope_per_reading=0.12)

        all_events = []
        for d in series:
            reading = _reading_from_dict(d)
            all_events.extend(service.process_reading(reading))

        drift_events = [e for e in all_events if e.anomaly_type == AnomalyType.DRIFT]
        assert len(drift_events) > 0
        assert all(e.variable == "temperature" for e in drift_events)


class TestEndToEndNoise:
    """High-noise temperature should be detected."""

    def test_noise_detected_in_simulated_data(self):
        service = AnomalyDetectionService(
            drift_window=10, noise_window=10,
            noise_warn_mult=3.0, noise_crit_mult=5.0,
            dropout_multiplier=3, dropout_baseline_count=5,
        )
        series = generate_stable_series(duration_min=30, interval_sec=60, seed=60)
        series = inject_noise(series, "temperature", noise_std=4.0, seed=61)

        all_events = []
        for d in series:
            reading = _reading_from_dict(d)
            all_events.extend(service.process_reading(reading))

        noise_events = [e for e in all_events if e.anomaly_type == AnomalyType.NOISE]
        assert len(noise_events) > 0
        assert all(e.variable == "temperature" for e in noise_events)


class TestEndToEndDropout:
    """Data gap should be detected as dropout."""

    def test_dropout_detected_in_simulated_data(self):
        service = AnomalyDetectionService(
            drift_window=10, noise_window=10,
            dropout_multiplier=3, dropout_baseline_count=5,
        )
        series = generate_stable_series(duration_min=30, interval_sec=60, seed=70)
        series = inject_gap(series, start_index=15, gap_count=8)

        all_events = []
        for d in series:
            reading = _reading_from_dict(d)
            all_events.extend(service.process_reading(reading))

        dropout_events = [e for e in all_events if e.anomaly_type == AnomalyType.DROPOUT]
        assert len(dropout_events) > 0
        assert dropout_events[0].detail["missed_readings"] >= 7


class TestEndToEndFromDatasetFiles:
    """Load pre-generated JSON datasets and verify detection."""

    DATASET_DIR = Path(__file__).parent.parent / "backend" / "simulation" / "datasets"

    def _load_and_run(self, filename):
        service = AnomalyDetectionService(
            drift_window=10, noise_window=10,
            dropout_multiplier=3, dropout_baseline_count=5,
        )
        filepath = self.DATASET_DIR / filename
        with open(filepath) as f:
            data = json.load(f)

        all_events = []
        for d in data["readings"]:
            reading = _reading_from_dict(d)
            all_events.extend(service.process_reading(reading))
        return all_events

    def test_stable_dataset_no_drift_or_dropout(self):
        events = self._load_and_run("stable_test.json")
        drift = [e for e in events if e.anomaly_type == AnomalyType.DRIFT]
        dropout = [e for e in events if e.anomaly_type == AnomalyType.DROPOUT]
        assert len(drift) == 0
        assert len(dropout) == 0

    def test_drift_dataset_has_drift(self):
        events = self._load_and_run("drift_test.json")
        drift = [e for e in events if e.anomaly_type == AnomalyType.DRIFT]
        assert len(drift) > 0

    def test_noise_dataset_has_noise(self):
        events = self._load_and_run("noise_test.json")
        noise = [e for e in events if e.anomaly_type == AnomalyType.NOISE]
        assert len(noise) > 0

    def test_missing_data_dataset_has_dropout(self):
        events = self._load_and_run("missing_data_test.json")
        dropout = [e for e in events if e.anomaly_type == AnomalyType.DROPOUT]
        assert len(dropout) > 0
