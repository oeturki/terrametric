# System Architecture

## Overview

```
Arduino (sensors) --> Bluetooth --> Raspberry Pi --> Node-RED --> ThingsBoard (live telemetry)
                                                        |
                                                        +--> Python Backend (FastAPI) --> Custom Web App (React)
```

## Layers

1. **Edge Layer** - Arduino + sensors (DHT11, PIR, LDR, Ultrasonic)
2. **Gateway Layer** - Raspberry Pi + Node-RED (Bluetooth receive, MQTT publish)
3. **Platform Layer** - ThingsBoard CE (device management, basic dashboards)
4. **Backend Layer** - Python FastAPI (business logic, derived metrics, auth, reports)
5. **Frontend Layer** - React web app (advanced dashboard, reports, session management)

## Data Flow

See README.md for the full data flow diagram.

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Microcontroller | Arduino (ATmega328P) |
| Sensors | DHT11, PIR, LDR, HC-SR04 |
| Communication | Bluetooth Classic (HC-05/06) |
| Gateway | Node-RED on Raspberry Pi |
| IoT Platform | ThingsBoard Community Edition |
| Backend | Python 3.11+, FastAPI, SQLAlchemy |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | React 19, Vite, Recharts |
| Testing | pytest |
