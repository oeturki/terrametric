# Anomaly Detection Module -- Design Document

**Owner:** Omer
**FR:** FR10 -- Anomaly Detection Layer
**Status:** Implementation in progress

---

## 1. Purpose

Detect data anomalies in real-time as sensor readings arrive from the Arduino via Node-RED. Three anomaly types are supported:

- **Drift** -- gradual sensor calibration loss over time
- **Noise** -- increased reading jitter from sensor degradation
- **Dropout** -- gaps in data from connectivity or power loss

Detection runs independently for each environmental variable: temperature, humidity, and light.

---

## 2. Hardware Context

| Sensor | Variable | Type | Accuracy | Notes |
|--------|----------|------|----------|-------|
| DHT11 | temperature | float | +/-2 C | Sends `null` on read failure. Updates every ~2s despite 200ms loop. |
| DHT11 | humidity | float | +/-5 %RH | Same physical sensor as temperature. |
| LDR (A0) | light | int 0-1023 | uncalibrated | Raw analog read. Inherently noisy. |
| PIR | movement | bool | n/a | Not used for anomaly detection. |
| HC-SR04 | distance | int cm | n/a | Not used for anomaly detection. |

The Arduino transmits JSON every 200ms. Node-RED forwards to the backend at a rate determined by its flow configuration. The anomaly detection module does not assume a fixed sampling rate -- it detects the interval dynamically.

---

## 3. Architecture

### 3.1 Class Diagram

```mermaid
classDiagram
    class Reading {
        +int id
        +int session_id
        +datetime timestamp
        +Optional~float~ temperature
        +Optional~float~ humidity
        +Optional~int~ light
        +Optional~bool~ movement
        +Optional~int~ distance
    }

    class AnomalyEvent {
        +datetime timestamp
        +int session_id
        +str variable
        +AnomalyType anomaly_type
        +AlertSeverity severity
        +str message
        +dict detail
    }

    class SensorProfile {
        +float baseline_noise
        +float drift_slope_threshold
        +str unit
    }

    class RollingBuffer {
        -int max_size
        -dict buffers
        +add(variable, timestamp, value) void
        +get_window(variable) list
        +get_timestamps(variable) list
        +size(variable) int
        +clear() void
    }

    class DriftDetector {
        -dict~str,SensorProfile~ profiles
        -int window_size
        +detect(buffer, variable, session_id) Optional~AnomalyEvent~
    }

    class NoiseDetector {
        -dict~str,SensorProfile~ profiles
        -int window_size
        -float warning_multiplier
        -float critical_multiplier
        +detect(buffer, variable, session_id) Optional~AnomalyEvent~
    }

    class DropoutDetector {
        -dict~str,datetime~ last_seen
        -float expected_interval_sec
        -int multiplier
        +detect(session_id, timestamp) Optional~AnomalyEvent~
    }

    class AnomalyDetectionService {
        -dict~int,RollingBuffer~ buffers
        -DriftDetector drift_detector
        -NoiseDetector noise_detector
        -DropoutDetector dropout_detector
        -list~str~ variables
        +process_reading(reading) list~AnomalyEvent~
        +get_anomaly_summary(session_id) dict
        +reset(session_id) void
    }

    AnomalyDetectionService --> RollingBuffer
    AnomalyDetectionService --> DriftDetector
    AnomalyDetectionService --> NoiseDetector
    AnomalyDetectionService --> DropoutDetector
    DriftDetector --> SensorProfile
    NoiseDetector --> SensorProfile
    DriftDetector ..> AnomalyEvent : creates
    NoiseDetector ..> AnomalyEvent : creates
    DropoutDetector ..> AnomalyEvent : creates
    AnomalyDetectionService ..> Reading : consumes
```

### 3.2 Sequence Diagram -- Real-time Processing

```mermaid
sequenceDiagram
    participant NR as Node-RED
    participant API as Telemetry API
    participant TS as TelemetryService
    participant ADS as AnomalyDetectionService
    participant DOD as DropoutDetector
    participant RB as RollingBuffer
    participant DD as DriftDetector
    participant ND as NoiseDetector
    participant DB as Database
    participant AS as AlertService

    NR->>API: POST /api/telemetry/readings
    API->>TS: store_reading(data)
    TS->>DB: INSERT reading
    TS->>ADS: process_reading(reading)

    Note over ADS: Step 1 - Check for data gap
    ADS->>DOD: detect(session_id, timestamp)
    DOD-->>ADS: [] or [DropoutEvent]

    Note over ADS: Step 2 - Handle null values
    alt temperature is null
        ADS-->>ADS: skip temp detection this cycle
    end

    Note over ADS: Step 3 - Buffer and detect per variable
    ADS->>RB: add("temperature", timestamp, value)
    ADS->>DD: detect(buffer, "temperature", session_id)
    DD-->>ADS: [] or [DriftEvent]
    ADS->>ND: detect(buffer, "temperature", session_id)
    ND-->>ADS: [] or [NoiseEvent]

    Note over ADS: Repeat for humidity and light

    Note over ADS: Step 4 - Persist and notify
    ADS->>DB: INSERT anomaly_events
    ADS->>AS: notify(anomaly_events)
    ADS-->>TS: list of AnomalyEvents
    TS-->>API: response with anomaly flags
```

### 3.3 Activity Diagram -- Per-Reading Processing

```mermaid
flowchart TD
    Start["New reading received"] --> CheckFirst{"First reading<br/>for session?"}
    CheckFirst -->|Yes| InitBuffer["Initialize buffer,<br/>store timestamp"]
    CheckFirst -->|No| CheckGap{"Gap > threshold?"}
    CheckGap -->|Yes| DropoutEvent["Create DROPOUT event"]
    CheckGap -->|No| Continue["Continue"]
    DropoutEvent --> Continue
    InitBuffer --> Continue
    Continue --> ForEachVar["For each variable:<br/>temperature, humidity, light"]
    ForEachVar --> CheckNull{"Value is null?"}
    CheckNull -->|Yes| SkipVar["Skip this variable"]
    CheckNull -->|No| AddBuffer["Add to rolling buffer"]
    AddBuffer --> CheckWindow{"Buffer >= window size?"}
    CheckWindow -->|No| NextVar["Next variable"]
    CheckWindow -->|Yes| RunDrift["Compute regression slope"]
    RunDrift --> DriftCheck{"abs slope > threshold?"}
    DriftCheck -->|Yes| DriftEvt["Create DRIFT event"]
    DriftCheck -->|No| RunNoise["Compute rolling std dev"]
    DriftEvt --> RunNoise
    RunNoise --> NoiseCheck{"std > multiplier * baseline?"}
    NoiseCheck -->|Yes| NoiseEvt["Create NOISE event"]
    NoiseCheck -->|No| NextVar
    NoiseEvt --> NextVar
    NextVar --> MoreVars{"More variables?"}
    MoreVars -->|Yes| ForEachVar
    MoreVars -->|No| ReturnEvents["Return all events"]
    SkipVar --> NextVar
```

---

## 4. Algorithm Specifications

### 4.1 Drift Detection -- Linear Regression Slope

**Problem:** Sensor calibration degrades over time. Readings gradually shift from truth.

**Method:** Fit a least-squares line to a sliding window of readings. If the slope exceeds a threshold, the sensor is drifting.

**Formula:**

Given N readings in the window (x = index, y = value):

```
slope = (N * sum(x*y) - sum(x) * sum(y)) / (N * sum(x^2) - sum(x)^2)
```

Implemented via `numpy.polyfit(x, y, 1)[0]`.

**Thresholds:**

| Variable | Threshold | Reasoning |
|----------|-----------|-----------|
| Temperature | 0.05 C/reading | At 1 reading/min, this is 3 C/hour -- abnormal for a sealed chamber |
| Humidity | 0.5 %RH/reading | DHT11 has +/-5%RH accuracy and high noise (std ~2.0). Threshold must exceed 3x the regression standard error for noise of this magnitude to avoid false positives. |
| Light | 3.0 units/reading | LDR is noisy; higher threshold avoids false positives |

**Window size:** 30 readings. Balances early detection vs false positives.

**Severity:** WARNING if slope is 1-2x threshold. CRITICAL if > 2x.

### 4.2 Noise Detection -- Rolling Standard Deviation

**Problem:** Sensor degradation causes readings to become increasingly jittery.

**Method:** Compute standard deviation of a sliding window. Compare against known baseline noise for the sensor.

**Formula:**

```
std = sqrt( (1/N) * sum((xi - mean)^2) )
```

Implemented via `numpy.std(values)`.

**Baselines (from datasheets and empirical observation):**

| Variable | Baseline Std Dev | Source |
|----------|-----------------|--------|
| Temperature | 0.5 C | DHT11 resolution is 1C; normal fluctuation ~0.5 |
| Humidity | 2.0 %RH | DHT11 accuracy +/-5%RH; normal jitter ~2 |
| Light | 20 raw units | Analog read noise on Arduino A0 |

**Multipliers:** WARNING at 3x baseline. CRITICAL at 5x baseline.

**Window size:** 10 readings. Short enough for fast detection, long enough for statistical significance.

### 4.3 Dropout Detection -- Timestamp Gap Analysis

**Problem:** Bluetooth disconnects, Pi crashes, or power outages cause data gaps.

**Method:** Compare the gap between consecutive reading timestamps against the expected interval.

**Formula:**

```
gap = current_timestamp - previous_timestamp
expected = median of first 20 inter-reading intervals (dynamic)
if gap > multiplier * expected: flag dropout
```

**Severity:** INFO if 3-5x expected. WARNING if 5-15x. CRITICAL if > 15x.

---

## 5. Integration Contracts

### Contract 1: Input from Telemetry Service (Bo)

Bo's `telemetry_service.store_reading()` calls `anomaly_service.process_reading(reading)` after persisting each reading.

### Contract 2: Output to Alert Service (Harini)

Each `AnomalyEvent` can optionally trigger an alert via `alert_service.create_alert()`.

### Contract 3: Output to Frontend (Chris)

REST endpoints:
- `GET /api/anomalies?session_id=X` -- paginated list of anomaly events
- `GET /api/anomalies/active?session_id=X` -- currently active anomalies

### Contract 4: Output to Report Service (Jena)

`get_anomaly_summary(session_id)` returns:
- Total count by anomaly type
- List of all events with timestamps
- Time ranges affected by each anomaly

### Contract 5: Interaction with ESI Service (Bo)

Design decision: ESI does NOT exclude anomaly-flagged readings. Anomalies are reported alongside ESI, not used to filter ESI input. This keeps the two modules independent.

---

## 6. Sensor Profiles

Rather than scattering thresholds across config, each sensor has a `SensorProfile`:

```python
SENSOR_PROFILES = {
    "temperature": SensorProfile(baseline_noise=0.5, drift_slope_threshold=0.05, unit="C"),
    "humidity":    SensorProfile(baseline_noise=2.0, drift_slope_threshold=0.5, unit="%RH"),
    "light":       SensorProfile(baseline_noise=20.0, drift_slope_threshold=3.0, unit="raw"),
}
```

If the team later swaps DHT11 for BME280, only the profile changes.

---

## 7. Performance

- **Per-reading cost:** 3 detectors x 3 variables = 9 checks. Each O(N) where N <= 30. Total ~270 ops. Negligible.
- **Memory:** 30 readings x 3 variables x 50 sessions = ~4500 floats = under 40KB.
- **Latency:** Sub-millisecond per reading. No blocking I/O in detection path.

---

## 8. Known Limitations

- **Buffer lost on restart.** Rolling window resets if backend restarts. Refills within 30 readings.
- **No cross-variable correlation.** Each variable analysed independently.
- **Dynamic interval estimation.** Dropout baseline computed from first 20 readings. Stale if rate changes mid-session.
- **DHT11 repeated values.** DHT11 updates every ~2s; faster polling produces duplicates that deflate noise std dev. Mitigated by deduplicating consecutive identical values.
- **LDR not calibrated.** Light thresholds in raw analog units, not lux.
- **No spike detection.** Deferred. Can be added as a 4th detector using z-score.

---

## 9. Design Decisions and Justifications

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|------------------------|-----|
| Drift algorithm | Linear regression slope | CUSUM, EWMA | Simplest to implement, explain, and test. CUSUM is better for detecting small shifts but harder to tune. |
| Noise algorithm | Rolling std dev | Wavelet decomposition, Kalman filter | Std dev is well-understood and sufficient for DHT11-class sensors. Wavelet is overkill. |
| Window units | Readings (not minutes) | Time-based windows | Decouples detection from sampling rate. Works regardless of Node-RED throttling. |
| Buffer persistence | In-memory only | Redis, DB-backed | University project scope. 30-reading refill time is acceptable. |
| Cross-variable detection | Not implemented | Correlation matrix | Scope control. Independent detection covers primary use cases. |
