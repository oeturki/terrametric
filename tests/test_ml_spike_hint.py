"""Regression: ML batch labels seasonal-looking bursts should still surface as spike when jump is dominant."""

from services.ml_classifier_service import ml_row_signals_instantaneous_spike


def test_ml_spike_hint_flags_large_light_jump():
    m = {
        "temperature": 22.0,
        "humidity": 50.0,
        "light": 900.0,
        "plant_height": 12.0,
        "dt_sec": 1.0,
        "d_temp": 0.05,
        "d_hum": 0.1,
        "d_light": 420.0,
        "roll_mean_temp": 22.0,
        "roll_std_temp": 0.2,
        "roll_mean_hum": 49.9,
        "roll_std_hum": 0.8,
        "roll_mean_light": 180.0,
        "roll_std_light": 4.0,
    }
    assert ml_row_signals_instantaneous_spike(m) is True


def test_ml_spike_hint_ignores_tiny_moves():
    m = {
        "d_temp": 0.1,
        "roll_std_temp": 1.0,
        "d_hum": 0.2,
        "roll_std_hum": 1.5,
        "d_light": 8.0,
        "roll_std_light": 6.0,
    }
    assert ml_row_signals_instantaneous_spike(m) is False
