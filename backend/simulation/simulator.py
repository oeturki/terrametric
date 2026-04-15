"""
Simulation Engine  [Owner: Omer]

Generates synthetic telemetry data and feeds it into the same backend pipeline
as live sensor data, enabling deterministic validation without hardware.

All generators produce lists of dicts with the same shape as a Reading:
  {"timestamp": ISO string, "temperature": float, "humidity": float, "light": int, ...}
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


def generate_stable_series(
    duration_min: int = 60,
    interval_sec: int = 60,
    setpoints: dict | None = None,
    noise_std: dict | None = None,
    seed: int = 42,
) -> list[dict]:
    """
    Generate a stable time series with small Gaussian noise around setpoints.
    This represents a healthy sensor in a well-controlled environment.
    """
    rng = np.random.default_rng(seed)
    setpoints = setpoints or {"temperature": 22.0, "humidity": 55.0, "light": 500}
    noise_std = noise_std or {"temperature": 0.3, "humidity": 1.5, "light": 10.0}

    readings = []
    base = datetime(2026, 4, 7, 10, 0, 0)
    n_points = (duration_min * 60) // interval_sec

    for i in range(n_points):
        ts = base + timedelta(seconds=i * interval_sec)
        readings.append({
            "timestamp": ts.isoformat(),
            "temperature": round(setpoints["temperature"] + rng.normal(0, noise_std["temperature"]), 1),
            "humidity": round(setpoints["humidity"] + rng.normal(0, noise_std["humidity"]), 1),
            "light": int(setpoints["light"] + rng.normal(0, noise_std["light"])),
            "movement": False,
            "distance": 30,
        })

    return readings


def inject_drift(
    readings: list[dict],
    variable: str,
    slope_per_reading: float,
    start_index: int = 0,
    end_index: int | None = None,
) -> list[dict]:
    """
    Add a linear drift to a specific variable starting from start_index.
    slope_per_reading is in units/reading (e.g. 0.1 C/reading).
    """
    end_index = end_index or len(readings)
    for i in range(start_index, min(end_index, len(readings))):
        offset = slope_per_reading * (i - start_index)
        if variable == "light":
            readings[i][variable] = int(readings[i][variable] + offset)
        else:
            readings[i][variable] = round(readings[i][variable] + offset, 1)
    return readings


def inject_noise(
    readings: list[dict],
    variable: str,
    noise_std: float,
    start_index: int = 0,
    end_index: int | None = None,
    seed: int = 123,
) -> list[dict]:
    """
    Replace a variable's values with high-noise versions (large std dev).
    """
    rng = np.random.default_rng(seed)
    end_index = end_index or len(readings)
    for i in range(start_index, min(end_index, len(readings))):
        base_value = readings[i][variable]
        noisy = base_value + rng.normal(0, noise_std)
        if variable == "light":
            readings[i][variable] = max(0, int(noisy))
        else:
            readings[i][variable] = round(float(noisy), 1)
    return readings


def inject_gap(
    readings: list[dict],
    start_index: int,
    gap_count: int,
) -> list[dict]:
    """
    Remove gap_count readings starting at start_index to simulate a data dropout.
    """
    return readings[:start_index] + readings[start_index + gap_count:]


def inject_spike(
    readings: list[dict],
    variable: str,
    count: int = 3,
    magnitude: float = 15.0,
    seed: int = 42,
) -> list[dict]:
    """
    Insert `count` extreme outlier spikes at random positions.
    Each spike adds +/- magnitude to the current value.
    """
    rng = np.random.default_rng(seed)
    indices = rng.choice(len(readings), size=min(count, len(readings)), replace=False)
    for idx in indices:
        sign = rng.choice([-1, 1])
        val = readings[idx][variable]
        spiked = val + sign * magnitude
        if variable == "light":
            readings[idx][variable] = max(0, int(spiked))
        else:
            readings[idx][variable] = round(float(spiked), 1)
    return readings


def inject_level_shift(
    readings: list[dict],
    variable: str,
    shift_amount: float = 8.0,
    start_fraction: float = 0.5,
) -> list[dict]:
    """
    Apply a permanent step change from start_fraction of the way through.
    Simulates a greenhouse door opening or heater failure.
    """
    start_idx = int(len(readings) * start_fraction)
    for i in range(start_idx, len(readings)):
        val = readings[i][variable]
        shifted = val + shift_amount
        if variable == "light":
            readings[i][variable] = max(0, int(shifted))
        else:
            readings[i][variable] = round(float(shifted), 1)
    return readings


def inject_correlation_break(
    readings: list[dict],
    seed: int = 42,
    start_fraction: float = 0.4,
    end_fraction: float = 0.7,
) -> list[dict]:
    """
    In the affected region, randomise humidity independently of temperature
    to break the natural temp-humidity correlation.
    """
    rng = np.random.default_rng(seed)
    start_idx = int(len(readings) * start_fraction)
    end_idx = int(len(readings) * end_fraction)
    for i in range(start_idx, end_idx):
        readings[i]["humidity"] = round(float(rng.uniform(20.0, 90.0)), 1)
    return readings


def save_dataset(readings: list[dict], filepath: str, description: str, **meta) -> None:
    """Save a dataset to JSON with metadata."""
    data = {
        "description": description,
        "generated_at": datetime.now().isoformat(),
        "count": len(readings),
        **meta,
        "readings": readings,
    }
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def generate_all_test_datasets(output_dir: str) -> None:
    """Generate all standard test datasets used by test_anomaly.py and test_simulation.py."""

    out = Path(output_dir)

    # 1. Stable (no anomalies)
    stable = generate_stable_series(duration_min=60, interval_sec=60, seed=42)
    save_dataset(
        stable, str(out / "stable_test.json"),
        "Stable baseline: 60 minutes at setpoints with normal sensor noise",
        setpoints={"temperature": 22.0, "humidity": 55.0, "light": 500},
    )

    # 2. Drift in temperature
    drift = generate_stable_series(duration_min=60, interval_sec=60, seed=43)
    drift = inject_drift(drift, "temperature", slope_per_reading=0.1)
    save_dataset(
        drift, str(out / "drift_test.json"),
        "FR10 Test B - Drift anomaly: temperature increasing 0.1C/reading for 60 readings",
        setpoints={"temperature": 22.0, "humidity": 55.0, "light": 500},
        expected_anomaly={"type": "drift", "variable": "temperature", "slope": 0.1},
    )

    # 3. High noise in temperature
    noisy = generate_stable_series(duration_min=60, interval_sec=60, seed=44)
    noisy = inject_noise(noisy, "temperature", noise_std=3.0, seed=45)
    save_dataset(
        noisy, str(out / "noise_test.json"),
        "FR10 - Noise anomaly: temperature with std=3.0 (6x baseline of 0.5)",
        setpoints={"temperature": 22.0, "humidity": 55.0, "light": 500},
        expected_anomaly={"type": "noise", "variable": "temperature", "noise_std": 3.0},
    )

    # 4. Data gap (dropout)
    gap = generate_stable_series(duration_min=60, interval_sec=60, seed=46)
    gap = inject_gap(gap, start_index=25, gap_count=10)
    save_dataset(
        gap, str(out / "missing_data_test.json"),
        "FR10 Test C - Dropout: 10 readings removed at index 25 (10-minute gap)",
        setpoints={"temperature": 22.0, "humidity": 55.0, "light": 500},
        expected_anomaly={"type": "dropout", "gap_start_index": 25, "gap_count": 10},
    )


if __name__ == "__main__":
    dataset_dir = str(Path(__file__).parent / "datasets")
    generate_all_test_datasets(dataset_dir)
    print(f"Datasets generated in {dataset_dir}")
