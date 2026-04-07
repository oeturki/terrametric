# Group 14 - Integrated Environmental Control & Research Integrity System

An IoT-based environmental monitoring and control system for plant and GMO research in indoor growing environments. The system combines continuous environmental sensing, automated regulation, and research-grade data logging into a single platform.

## Architecture

```
Arduino (sensors)
    |
    | JSON via Bluetooth
    v
Raspberry Pi
    |
    +--> Node-RED --> MQTT --> ThingsBoard CE (live telemetry dashboard)
    |
    +--> Python Backend (FastAPI)
              |
              +--> Database (SQLite / PostgreSQL)
              |
              +--> Custom React Dashboard (advanced features)
```

## Project Structure

```
group-14-cm2305-2211/
|
├── arduino/                        # Embedded firmware
│   ├── arduino_bluetooth/          # Main sensor sketch (DHT11, PIR, LDR, Ultrasonic)
│   └── Group14Project/             # Legacy sketch
|
├── node-red/                       # Gateway middleware
│   └── flows.json                  # Export from Pi's Node-RED
|
├── backend/                        # Python backend (FastAPI)
│   ├── main.py                     # App entry point
│   ├── config.py                   # Setpoints, thresholds, DB config
│   ├── database.py                 # DB engine setup
│   ├── api/                        # REST API routes
│   │   ├── telemetry.py            # FR1/FR2
│   │   ├── alerts.py               # FR3
│   │   ├── control.py              # FR4
│   │   ├── camera.py               # FR5
│   │   ├── auth.py                 # FR6
│   │   ├── plants.py               # FR7
│   │   ├── sessions.py             # Session management
│   │   └── reports.py              # FR11
│   ├── services/                   # Business logic
│   │   ├── telemetry_service.py    # FR1/FR2: Ingest + query readings
│   │   ├── alert_service.py        # FR3: Threshold detection
│   │   ├── control_service.py      # FR4: Feedback control
│   │   ├── camera_service.py       # FR5: Image capture
│   │   ├── plant_service.py        # FR7: QR + plant tracking
│   │   ├── esi_service.py          # FR8: Environmental Stability Index
│   │   ├── stress_service.py       # FR9: Cumulative stress
│   │   ├── anomaly_service.py      # FR10: Spike/drift/gap detection
│   │   └── report_service.py       # FR11: Integrity reports
│   ├── models/                     # Database models
│   └── simulation/                 # Simulation & replay engine
│       ├── simulator.py            # Synthetic data generator
│       ├── replay.py               # Session replay
│       └── datasets/               # Test scenario data files
|
├── frontend/                       # React web app (Vite)
│   ├── src/
│   │   ├── components/             # UI components (one per feature)
│   │   ├── pages/                  # Dashboard, Sessions, Plants, Reports, Login
│   │   └── services/api.js         # HTTP client
│   ├── package.json
│   └── vite.config.js
|
├── tests/                          # Validation tests (pytest)
│   ├── test_esi.py                 # FR8
│   ├── test_stress.py              # FR9
│   ├── test_anomaly.py             # FR10
│   ├── test_alerts.py              # FR3
│   ├── test_reports.py             # FR11
│   └── test_simulation.py          # Simulation pipeline
|
└── docs/
    ├── architecture.md
    └── setup-guide.md
```

## Team Responsibilities(Ignore this one as it is AI generated, make changes to it for it to reflect your current responsibilities)

| Member    | Area                              | Key Files                                              |
|-----------|-----------------------------------|--------------------------------------------------------|
| Omer      | Anomaly detection + Simulation    | `services/anomaly_service.py`, `simulation/`, tests    |
| Bo        | Telemetry, ESI, Stress metrics    | `services/telemetry_service.py`, `esi_service.py`, `stress_service.py` |
| Harini    | Alerts + Documentation            | `services/alert_service.py`, `api/alerts.py`, `docs/`  |
| Chris     | Frontend dashboard                | `frontend/src/`, components, pages                      |
| Jena      | Reports + Visualisation           | `services/report_service.py`, `ReportViewer.jsx`        |
| Mohammed  | Control logic + NFR validation    | `services/control_service.py`, `api/control.py`         |
| Osamah    | Camera + Plant tracking           | `services/camera_service.py`, `plant_service.py`        |

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Arduino

Open `arduino/arduino_bluetooth/arduino_bluetooth.ino` in Arduino IDE and upload.

### Tests

```bash
pytest tests/
```

See `docs/setup-guide.md` for full setup instructions.

## Functional Requirements

| ID   | Requirement                          | Status |
|------|--------------------------------------|--------|
| FR1  | Environmental Monitoring             | Scaffold |
| FR2  | Data Logging & Visualisation         | Scaffold |
| FR3  | Alerts & Early Warning               | Scaffold |
| FR4  | Automated Environmental Control      | Scaffold |
| FR5  | Camera-Based Visual Monitoring       | Scaffold |
| FR6  | User & Data Management               | Scaffold |
| FR7  | Plant / Sample Identification        | Scaffold |
| FR8  | Environmental Stability Index (ESI)  | Scaffold |
| FR9  | Cumulative Stress Tracking           | Scaffold |
| FR10 | Anomaly Detection Layer              | Scaffold |
| FR11 | Session Integrity Report             | Scaffold |
| FR12 | Time-in-Tolerance Visual Overlay     | Scaffold |
