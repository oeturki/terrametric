# Setup Guide

## Prerequisites

- Python 3.11+
- Node.js 20+
- Arduino IDE
- Raspberry Pi with Node-RED and ThingsBoard CE installed

## Backend Setup

### Windows laptop (single command)

From the **`backend`** folder:

```bat
start_terrametric_laptop.bat
```

This creates **`venv`** on first run, **`pip install -r requirements.txt`** each launch, then serves app + API at **http://127.0.0.1:8000**.  

Checklist + URLs: **`docs/laptop-smoke-test.md`** · readiness: http://127.0.0.1:8000/api/health/ready

API docs: http://127.0.0.1:8000/docs  

### Manual (any OS)

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at http://localhost:8000

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:5173
API calls are proxied to the backend.

## Arduino

Open `arduino/arduino_bluetooth/arduino_bluetooth.ino` in Arduino IDE and upload to board.

## Raspberry Pi (live Arduino → backend)

To feed real HC-05 Bluetooth readings into the backend running on a Pi, follow
[pi-setup.md](pi-setup.md). It covers pairing the HC-05, binding `/dev/rfcomm0`,
and running `pi/arduino_bridge.py` which forwards each JSON line to
`POST /api/telemetry/ingest`.

## Node-RED

Import `node-red/flows.json` into Node-RED on the Raspberry Pi.
(Export flows from Pi: Menu > Export > Download)

## Running Tests

```bash
cd tests
pytest
```
