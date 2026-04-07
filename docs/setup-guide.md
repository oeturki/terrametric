# Setup Guide

## Prerequisites

- Python 3.11+
- Node.js 20+
- Arduino IDE
- Raspberry Pi with Node-RED and ThingsBoard CE installed

## Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at http://localhost:8000
API docs at http://localhost:8000/docs

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

## Node-RED

Import `node-red/flows.json` into Node-RED on the Raspberry Pi.
(Export flows from Pi: Menu > Export > Download)

## Running Tests

```bash
cd tests
pytest
```
