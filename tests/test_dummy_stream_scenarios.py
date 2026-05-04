"""Smoke tests for dummy-stream scenario profiles."""

from datetime import datetime, timedelta
from typing import get_args

from schemas.session_schema import ScenarioName
from services.dummy_stream import SCENARIOS, ScenarioContext, generate_reading


def test_all_scenario_name_keys_registered_in_generators():
    for key in get_args(ScenarioName):
        assert key in SCENARIOS


def test_generate_reading_accepts_every_scenario_name():
    t0 = datetime(2026, 4, 24, 12, 0, 0)
    ctx = ScenarioContext(started_at=t0)
    for scenario in get_args(ScenarioName):
        r = generate_reading(scenario, t0 + timedelta(minutes=15), ctx)
        assert r.timestamp >= t0


def test_missing_temp_readings_sometimes_returns_none_temperature():
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    ctx = ScenarioContext(started_at=t0)
    seen_none = False
    seen_float = False
    for minute in range(300):
        r = generate_reading("missing_temp_readings", t0 + timedelta(minutes=minute), ctx)
        if r.temperature is None:
            seen_none = True
        elif isinstance(r.temperature, float):
            seen_float = True
        assert r.humidity is not None
        assert r.light is not None
        if seen_none and seen_float:
            break
    assert seen_none and seen_float


def test_stable_never_reports_none_temperature():
    t0 = datetime(2026, 4, 24, 8, 0, 0)
    ctx = ScenarioContext(started_at=t0)
    for minute in range(120):
        r = generate_reading("stable", t0 + timedelta(minutes=minute), ctx)
        assert r.temperature is not None


def test_light_spike_burst_adds_jump_on_nth_insert_aligned_row():
    """Bursts tie to insert ordinal (not wall clock) so spike detector sees outliers soon after stream start."""

    noon = datetime(2026, 6, 15, 12, 0, 0)
    ctx = ScenarioContext(started_at=noon, stream_interval_sec=1.0, successful_inserts_prior=5)
    r = generate_reading("light_spike_burst", noon, ctx)
    assert r.light is not None
    base = float(r.light)
    ctx.successful_inserts_prior = 11
    r2 = generate_reading("light_spike_burst", noon + timedelta(seconds=1), ctx)
    assert r2.light is not None
    assert float(r2.light) >= base + 200.0
