"""
FR10 - Anomaly Detection unit tests.  [Owner: Omer]

Tests are written BEFORE implementation (TDD). Each test uses deterministic
synthetic data with a known ground-truth expected result.

Run with: pytest tests/test_anomaly.py -v
"""

import sys
import os
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.detectors.rolling_buffer import RollingBuffer
from services.detectors.drift import DriftDetector
from services.detectors.noise import NoiseDetector
from services.detectors.dropout import DropoutDetector
from services.detectors.spike import SpikeDetector
from services.detectors.correlation import CorrelationDetector
from services.detectors.cusum import CUSUMDetector
from services.detectors.ewma import EWMADetector
from services.detectors.seasonal import SeasonalDetector
from services.detectors.base import SensorProfile, AnomalyEvent, SENSOR_PROFILES, Reading
from services.anomaly_service import AnomalyDetectionService
from enums import AnomalyType, AlertSeverity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_timestamp(minute: int) -> datetime:
    """Create a timestamp at a given minute offset from a fixed base."""
    return datetime(2026, 4, 7, 10, 0, 0) + timedelta(minutes=minute)


def make_reading(session_id, minute, temperature=22.0, humidity=55.0, light=500):
    """Create a Reading dataclass for testing."""
    return Reading(
        session_id=session_id,
        timestamp=make_timestamp(minute),
        temperature=temperature,
        humidity=humidity,
        light=light,
        movement=False,
        distance=30,
    )


# ===========================================================================
# ROLLING BUFFER TESTS
# ===========================================================================

class TestRollingBuffer:

    def test_add_and_retrieve(self):
        buf = RollingBuffer(max_size=5)
        t = make_timestamp(0)
        buf.add("temperature", t, 22.0)
        assert buf.size("temperature") == 1
        assert buf.get_values("temperature") == [22.0]
        assert buf.get_timestamps("temperature") == [t]

    def test_max_size_eviction(self):
        buf = RollingBuffer(max_size=3)
        for i in range(5):
            buf.add("temperature", make_timestamp(i), float(i))
        assert buf.size("temperature") == 3
        assert buf.get_values("temperature") == [2.0, 3.0, 4.0]

    def test_multiple_variables_independent(self):
        buf = RollingBuffer(max_size=10)
        buf.add("temperature", make_timestamp(0), 22.0)
        buf.add("humidity", make_timestamp(0), 55.0)
        assert buf.size("temperature") == 1
        assert buf.size("humidity") == 1

    def test_empty_variable_returns_empty(self):
        buf = RollingBuffer(max_size=5)
        assert buf.get_values("nonexistent") == []
        assert buf.size("nonexistent") == 0

    def test_clear(self):
        buf = RollingBuffer(max_size=5)
        buf.add("temperature", make_timestamp(0), 22.0)
        buf.clear()
        assert buf.size("temperature") == 0


# ===========================================================================
# DRIFT DETECTOR TESTS
# ===========================================================================

class TestDriftDetector:

    @pytest.fixture
    def detector(self):
        return DriftDetector(profiles=SENSOR_PROFILES, window_size=10)

    def test_no_drift_stable_readings(self, detector):
        """10 readings oscillating around 22.0 -> slope ~ 0 -> no drift."""
        buf = RollingBuffer(max_size=10)
        values = [22.1, 21.9, 22.2, 21.8, 22.0, 22.1, 21.9, 22.0, 22.2, 21.8]
        for i, v in enumerate(values):
            buf.add("temperature", make_timestamp(i), v)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is None

    def test_drift_detected_increasing(self, detector):
        """10 readings increasing at 0.1C/reading -> slope=0.1 > threshold=0.05."""
        buf = RollingBuffer(max_size=10)
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0 + i * 0.1)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is not None
        assert result.anomaly_type == AnomalyType.DRIFT
        assert result.variable == "temperature"
        assert result.detail["slope"] == pytest.approx(0.1, abs=0.001)

    def test_drift_detected_decreasing(self, detector):
        """10 readings decreasing at -0.1C/reading -> drift flagged."""
        buf = RollingBuffer(max_size=10)
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0 - i * 0.1)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is not None
        assert result.detail["slope"] == pytest.approx(-0.1, abs=0.001)

    def test_drift_severity_warning(self, detector):
        """Slope 1.5x threshold -> WARNING."""
        buf = RollingBuffer(max_size=10)
        slope = 0.05 * 1.5  # 1.5x threshold
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0 + i * slope)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is not None
        assert result.severity == AlertSeverity.WARNING

    def test_drift_severity_critical(self, detector):
        """Slope > 2x threshold -> CRITICAL."""
        buf = RollingBuffer(max_size=10)
        slope = 0.05 * 2.5  # 2.5x threshold
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0 + i * slope)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is not None
        assert result.severity == AlertSeverity.CRITICAL

    def test_window_not_full_returns_none(self, detector):
        """Less than window_size readings -> skip detection."""
        buf = RollingBuffer(max_size=10)
        for i in range(5):
            buf.add("temperature", make_timestamp(i), 22.0 + i * 0.2)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is None

    def test_humidity_drift(self, detector):
        """Humidity drifting at 0.6%RH/reading > threshold 0.5 -> flagged."""
        buf = RollingBuffer(max_size=10)
        for i in range(10):
            buf.add("humidity", make_timestamp(i), 55.0 + i * 0.6)

        result = detector.detect(buf, "humidity", session_id=1)
        assert result is not None
        assert result.variable == "humidity"


# ===========================================================================
# NOISE DETECTOR TESTS
# ===========================================================================

class TestNoiseDetector:

    @pytest.fixture
    def detector(self):
        return NoiseDetector(
            profiles=SENSOR_PROFILES,
            window_size=10,
            warning_multiplier=3.0,
            critical_multiplier=5.0,
        )

    def test_no_noise_normal_readings(self, detector):
        """Std dev ~0.17 (well below 3x baseline of 0.5) -> no anomaly."""
        buf = RollingBuffer(max_size=10)
        values = [22.0, 22.3, 21.8, 22.1, 21.9, 22.2, 21.7, 22.0, 22.1, 21.9]
        for i, v in enumerate(values):
            buf.add("temperature", make_timestamp(i), v)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is None

    def test_noise_warning(self, detector):
        """Std dev ~1.8 (3.6x baseline of 0.5) -> WARNING."""
        buf = RollingBuffer(max_size=10)
        values = [22.0, 24.0, 20.0, 23.5, 20.5, 24.0, 20.0, 23.0, 21.0, 24.0]
        for i, v in enumerate(values):
            buf.add("temperature", make_timestamp(i), v)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is not None
        assert result.anomaly_type == AnomalyType.NOISE
        assert result.severity == AlertSeverity.WARNING

    def test_noise_critical(self, detector):
        """Std dev ~4.5 (9x baseline of 0.5) -> CRITICAL."""
        buf = RollingBuffer(max_size=10)
        values = [22.0, 30.0, 15.0, 28.0, 16.0, 29.0, 14.0, 27.0, 17.0, 30.0]
        for i, v in enumerate(values):
            buf.add("temperature", make_timestamp(i), v)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is not None
        assert result.severity == AlertSeverity.CRITICAL

    def test_window_not_full_returns_none(self, detector):
        buf = RollingBuffer(max_size=10)
        for i in range(5):
            buf.add("temperature", make_timestamp(i), 22.0 + i * 5)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is None

    def test_deduplicate_consecutive_identical(self, detector):
        """All identical values (e.g. DHT11 repeats) -> fewer than 3 unique -> skip."""
        buf = RollingBuffer(max_size=10)
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0)

        result = detector.detect(buf, "temperature", session_id=1)
        assert result is None

    def test_light_noise(self, detector):
        """Light with std ~80 (4x baseline of 20) -> WARNING."""
        buf = RollingBuffer(max_size=10)
        values = [500, 600, 400, 650, 350, 620, 380, 640, 360, 610]
        for i, v in enumerate(values):
            buf.add("light", make_timestamp(i), float(v))

        result = detector.detect(buf, "light", session_id=1)
        assert result is not None
        assert result.variable == "light"


# ===========================================================================
# DROPOUT DETECTOR TESTS
# ===========================================================================

class TestDropoutDetector:

    @pytest.fixture
    def detector(self):
        return DropoutDetector(multiplier=3, baseline_count=5)

    def _establish_baseline(self, detector, session_id=1, interval_sec=60):
        """Send enough readings to establish the expected interval baseline."""
        base = datetime(2026, 4, 7, 10, 0, 0)
        for i in range(6):
            t = base + timedelta(seconds=i * interval_sec)
            detector.detect(session_id, t)

    def test_first_reading_no_event(self, detector):
        result = detector.detect(1, make_timestamp(0))
        assert result is None

    def test_normal_interval_no_event(self, detector):
        self._establish_baseline(detector)
        base = datetime(2026, 4, 7, 10, 0, 0)
        t = base + timedelta(seconds=6 * 60)
        result = detector.detect(1, t)
        assert result is None

    def test_dropout_detected(self, detector):
        """Gap of 5 minutes (5x expected 60s) -> WARNING."""
        self._establish_baseline(detector)
        base = datetime(2026, 4, 7, 10, 0, 0)
        t = base + timedelta(seconds=6 * 60 + 300)  # 5-min gap after last
        result = detector.detect(1, t)
        assert result is not None
        assert result.anomaly_type == AnomalyType.DROPOUT
        assert result.severity == AlertSeverity.WARNING
        assert result.detail["missed_readings"] >= 4

    def test_large_dropout_critical(self, detector):
        """Gap of 20 minutes (20x expected 60s) -> CRITICAL."""
        self._establish_baseline(detector)
        base = datetime(2026, 4, 7, 10, 0, 0)
        t = base + timedelta(seconds=6 * 60 + 1200)
        result = detector.detect(1, t)
        assert result is not None
        assert result.severity == AlertSeverity.CRITICAL

    def test_small_dropout_info(self, detector):
        """Gap of 3.5x expected -> INFO."""
        self._establish_baseline(detector)
        base = datetime(2026, 4, 7, 10, 0, 0)
        t = base + timedelta(seconds=6 * 60 + 210)  # 3.5 * 60 = 210
        result = detector.detect(1, t)
        assert result is not None
        assert result.severity == AlertSeverity.INFO

    def test_separate_sessions_independent(self, detector):
        """Different sessions maintain separate baselines."""
        self._establish_baseline(detector, session_id=1, interval_sec=60)
        self._establish_baseline(detector, session_id=2, interval_sec=30)

        base1 = datetime(2026, 4, 7, 10, 0, 0)
        base2 = datetime(2026, 4, 7, 10, 0, 0)

        # Session 1: normal 60s gap -> no dropout
        result1 = detector.detect(1, base1 + timedelta(seconds=6 * 60 + 60))
        assert result1 is None

        # Session 2: 60s gap when baseline is 30s -> that's only 2x, not over 3x threshold
        result2 = detector.detect(2, base2 + timedelta(seconds=6 * 30 + 60))
        assert result2 is None

    def test_reset_clears_state(self, detector):
        self._establish_baseline(detector)
        detector.reset(1)
        result = detector.detect(1, make_timestamp(99))
        assert result is None  # first reading after reset, no comparison


# ===========================================================================
# ANOMALY DETECTION SERVICE (ORCHESTRATOR) TESTS
# ===========================================================================

class TestAnomalyDetectionService:

    @pytest.fixture
    def service(self):
        return AnomalyDetectionService(
            drift_window=10,
            noise_window=10,
            noise_warn_mult=3.0,
            noise_crit_mult=5.0,
            dropout_multiplier=3,
            dropout_baseline_count=5,
        )

    def test_stable_readings_no_events(self, service):
        """30 stable readings -> no anomalies."""
        events = []
        for i in range(30):
            r = make_reading(1, i, temperature=22.0, humidity=55.0, light=500)
            events.extend(service.process_reading(r))
        assert len(events) == 0

    def test_drift_detected_through_service(self, service):
        """Feed drifting temperature -> service reports drift events."""
        all_events = []
        for i in range(15):
            r = make_reading(1, i, temperature=22.0 + i * 0.15)
            all_events.extend(service.process_reading(r))

        drift_events = [e for e in all_events if e.anomaly_type == AnomalyType.DRIFT]
        assert len(drift_events) > 0

    def test_null_temperature_skipped(self, service):
        """Reading with null temperature -> no crash, no temp anomaly."""
        for i in range(15):
            r = make_reading(1, i)
            r.temperature = None
            events = service.process_reading(r)
            temp_events = [e for e in events if e.variable == "temperature"]
            assert len(temp_events) == 0

    def test_dropout_detected_through_service(self, service):
        """Feed readings with a gap -> dropout detected."""
        all_events = []
        # Establish baseline (6 readings at 1-min intervals)
        for i in range(6):
            r = make_reading(1, i)
            all_events.extend(service.process_reading(r))

        # Jump 10 minutes
        r = make_reading(1, 16)
        all_events.extend(service.process_reading(r))

        dropout_events = [e for e in all_events if e.anomaly_type == AnomalyType.DROPOUT]
        assert len(dropout_events) > 0

    def test_reset_clears_session(self, service):
        """After reset, buffer and dropout state are cleared."""
        for i in range(5):
            service.process_reading(make_reading(1, i))
        service.reset(1)
        # First reading after reset should not trigger dropout
        events = service.process_reading(make_reading(1, 99))
        dropout_events = [e for e in events if e.anomaly_type == AnomalyType.DROPOUT]
        assert len(dropout_events) == 0

    def test_anomaly_summary(self, service):
        """Summary correctly counts events by type and variable."""
        events = [
            AnomalyEvent(
                timestamp=make_timestamp(0), session_id=1, variable="temperature",
                anomaly_type=AnomalyType.DRIFT, severity=AlertSeverity.WARNING,
                message="test", detail={},
            ),
            AnomalyEvent(
                timestamp=make_timestamp(1), session_id=1, variable="humidity",
                anomaly_type=AnomalyType.NOISE, severity=AlertSeverity.CRITICAL,
                message="test", detail={},
            ),
        ]
        summary = service.get_anomaly_summary(1, events)
        assert summary["total_count"] == 2
        assert summary["by_type"]["drift"] == 1
        assert summary["by_type"]["noise"] == 1
        assert summary["by_variable"]["temperature"] == 1
        assert summary["by_variable"]["humidity"] == 1


# ===========================================================================
# SPIKE DETECTOR TESTS
# ===========================================================================

class TestSpikeDetector:

    @pytest.fixture
    def detector(self):
        return SpikeDetector(profiles=SENSOR_PROFILES, warning_z=4.0, critical_z=6.0)

    def test_normal_reading_no_spike(self, detector):
        """A value close to the mean should not trigger a spike."""
        buf = RollingBuffer(max_size=30)
        for i in range(20):
            buf.add("temperature", make_timestamp(i), 22.0 + (i % 3) * 0.1)
        reading = make_reading(1, 20, temperature=22.2)
        events = detector.detect_reading(reading, buf, session_id=1)
        assert len(events) == 0

    def test_spike_detected_high(self, detector):
        """A value far above the mean should trigger a spike."""
        buf = RollingBuffer(max_size=30)
        for i in range(20):
            buf.add("temperature", make_timestamp(i), 22.0)
        reading = make_reading(1, 20, temperature=40.0)
        events = detector.detect_reading(reading, buf, session_id=1)
        spike_events = [e for e in events if e.anomaly_type == AnomalyType.SPIKE and e.variable == "temperature"]
        assert len(spike_events) >= 1

    def test_hard_bounds_critical(self, detector):
        """A value outside physical sensor range is always CRITICAL."""
        buf = RollingBuffer(max_size=30)
        for i in range(6):
            buf.add("temperature", make_timestamp(i), 22.0)
        reading = make_reading(1, 6, temperature=-15.0)
        events = detector.detect_reading(reading, buf, session_id=1)
        temp_spikes = [e for e in events if e.variable == "temperature"]
        assert any(e.severity == AlertSeverity.CRITICAL for e in temp_spikes)

    def test_not_enough_data_skips(self, detector):
        """Less than MIN_BUFFER_SIZE readings should not trigger z-score spike."""
        buf = RollingBuffer(max_size=30)
        for i in range(3):
            buf.add("temperature", make_timestamp(i), 22.0)
        reading = make_reading(1, 3, temperature=30.0)
        events = detector.detect_reading(reading, buf, session_id=1)
        z_events = [e for e in events if e.detail.get("reason") != "hard_bounds"]
        assert len(z_events) == 0


# ===========================================================================
# CORRELATION DETECTOR TESTS
# ===========================================================================

class TestCorrelationDetector:

    @pytest.fixture
    def detector(self):
        return CorrelationDetector(
            window_size=10,
            warning_threshold=0.3,
            critical_threshold=0.1,
            cooldown=0,
        )

    def test_correlated_readings_no_alert(self, detector):
        """Temp and humidity that move together should not trigger."""
        buf = RollingBuffer(max_size=20)
        for i in range(15):
            t = 22.0 + i * 0.2
            h = 55.0 - i * 0.3
            buf.add("temperature", make_timestamp(i), t)
            buf.add("humidity", make_timestamp(i), h)
        reading = make_reading(1, 15, temperature=25.0, humidity=50.5)
        events = detector.detect_reading(reading, buf, session_id=1)
        assert len(events) == 0

    def test_uncorrelated_readings_alert(self, detector):
        """Random humidity (not tracking temperature) should trigger."""
        import numpy as np
        rng = np.random.default_rng(42)
        buf = RollingBuffer(max_size=20)
        for i in range(15):
            t = 22.0 + i * 0.1
            h = rng.uniform(30, 80)
            buf.add("temperature", make_timestamp(i), t)
            buf.add("humidity", make_timestamp(i), h)
        reading = make_reading(1, 15, temperature=23.5, humidity=rng.uniform(30, 80))
        events = detector.detect_reading(reading, buf, session_id=1)
        corr_events = [e for e in events if e.anomaly_type == AnomalyType.CORRELATION]
        assert len(corr_events) >= 1

    def test_not_enough_data_no_alert(self, detector):
        """Not enough readings to compute correlation should not trigger."""
        buf = RollingBuffer(max_size=20)
        for i in range(5):
            buf.add("temperature", make_timestamp(i), 22.0)
            buf.add("humidity", make_timestamp(i), 55.0)
        reading = make_reading(1, 5)
        events = detector.detect_reading(reading, buf, session_id=1)
        assert len(events) == 0


# ===========================================================================
# CUSUM DETECTOR TESTS
# ===========================================================================

class TestCUSUMDetector:

    @pytest.fixture
    def detector(self):
        return CUSUMDetector(profiles=SENSOR_PROFILES, min_readings=5)

    def test_stable_readings_no_shift(self, detector):
        """Stable readings should not trigger a level shift."""
        buf = RollingBuffer(max_size=30)
        events = []
        for i in range(30):
            buf.add("temperature", make_timestamp(i), 22.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i)
            events.extend(detector.detect_reading(reading, buf, session_id=1))
        shift_events = [e for e in events if e.anomaly_type == AnomalyType.LEVEL_SHIFT]
        assert len(shift_events) == 0

    def test_step_change_detected(self, detector):
        """An abrupt step up in temperature should trigger a level shift."""
        buf = RollingBuffer(max_size=30)
        events = []
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i)
            events.extend(detector.detect_reading(reading, buf, session_id=1))
        for i in range(10, 25):
            buf.add("temperature", make_timestamp(i), 30.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i, temperature=30.0)
            events.extend(detector.detect_reading(reading, buf, session_id=1))
        shift_events = [e for e in events if e.anomaly_type == AnomalyType.LEVEL_SHIFT and e.variable == "temperature"]
        assert len(shift_events) >= 1

    def test_reset_clears_state(self, detector):
        """After reset, CUSUM accumulators should be cleared."""
        buf = RollingBuffer(max_size=30)
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i)
            detector.detect_reading(reading, buf, session_id=1)
        detector.reset(session_id=1)
        assert "1" not in detector._s_high


# ===========================================================================
# EWMA DETECTOR TESTS
# ===========================================================================

class TestEWMADetector:

    @pytest.fixture
    def detector(self):
        return EWMADetector(profiles=SENSOR_PROFILES, lam=0.2, L=3.0, min_readings=5, cooldown=0)

    def test_stable_readings_no_breach(self, detector):
        """Stable readings around setpoint should stay within EWMA control limits."""
        buf = RollingBuffer(max_size=30)
        events = []
        for i in range(30):
            buf.add("temperature", make_timestamp(i), 22.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i)
            events.extend(detector.detect_reading(reading, buf, session_id=1))
        ewma_events = [e for e in events if e.anomaly_type == AnomalyType.EWMA_BREACH]
        assert len(ewma_events) == 0

    def test_sustained_shift_triggers_breach(self, detector):
        """Sustained readings well above the mean should breach EWMA limits."""
        buf = RollingBuffer(max_size=30)
        events = []
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i)
            events.extend(detector.detect_reading(reading, buf, session_id=1))
        for i in range(10, 30):
            buf.add("temperature", make_timestamp(i), 28.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i, temperature=28.0)
            events.extend(detector.detect_reading(reading, buf, session_id=1))
        ewma_events = [e for e in events if e.anomaly_type == AnomalyType.EWMA_BREACH]
        assert len(ewma_events) >= 1

    def test_reset_clears_ewma_state(self, detector):
        """Reset should clear all per-session state."""
        buf = RollingBuffer(max_size=30)
        for i in range(10):
            buf.add("temperature", make_timestamp(i), 22.0)
            buf.add("humidity", make_timestamp(i), 55.0)
            buf.add("light", make_timestamp(i), 500.0)
            reading = make_reading(1, i)
            detector.detect_reading(reading, buf, session_id=1)
        detector.reset(session_id=1)
        assert "1" not in detector._ewma


# ===========================================================================
# SEASONAL DETECTOR TESTS
# ===========================================================================

class TestSeasonalDetector:

    @pytest.fixture
    def detector(self):
        return SeasonalDetector(
            threshold_sigma=3.0,
            critical_sigma=5.0,
            min_per_hour=3,
            min_hours=2,
        )

    def test_learning_phase_no_alerts(self, detector):
        """During the learning phase (not enough data), no alerts should fire."""
        reading = Reading(
            session_id=1,
            timestamp=datetime(2026, 4, 7, 10, 0, 0),
            temperature=22.0, humidity=55.0, light=500,
        )
        events = detector.detect_reading(reading, None, session_id=1)
        assert len(events) == 0

    def test_normal_reading_after_baseline_no_alert(self, detector):
        """After learning, a value within normal range for the hour should pass."""
        base = datetime(2026, 4, 7, 0, 0, 0)
        for hour in range(3):
            for rep in range(4):
                r = Reading(
                    session_id=1,
                    timestamp=base.replace(hour=hour, minute=rep),
                    temperature=22.0, humidity=55.0,
                    light=500 + hour * 10,
                )
                detector.detect_reading(r, None, session_id=1)

        test_reading = Reading(
            session_id=1,
            timestamp=base.replace(hour=1, minute=30),
            temperature=22.0, humidity=55.0,
            light=512,
        )
        events = detector.detect_reading(test_reading, None, session_id=1)
        assert len(events) == 0

    def test_abnormal_light_after_baseline_alerts(self, detector):
        """After learning, a value way outside expected should fire."""
        base = datetime(2026, 4, 7, 0, 0, 0)
        for hour in range(3):
            for rep in range(4):
                r = Reading(
                    session_id=1,
                    timestamp=base.replace(hour=hour, minute=rep),
                    temperature=22.0, humidity=55.0,
                    light=500,
                )
                detector.detect_reading(r, None, session_id=1)

        test_reading = Reading(
            session_id=1,
            timestamp=base.replace(hour=0, minute=30),
            temperature=22.0, humidity=55.0,
            light=900,
        )
        events = detector.detect_reading(test_reading, None, session_id=1)
        seasonal_events = [e for e in events if e.anomaly_type == AnomalyType.SEASONAL]
        assert len(seasonal_events) >= 1
