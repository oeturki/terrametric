# TerraMetric — System features (for presentations & onboarding)

This document summarises **what the Group 14 system implements** and **why** each part exists, so team members can prepare slides, demos, or reports without spelunking the whole repo.

**Related docs:** [architecture.md](architecture.md), [setup-guide.md](setup-guide.md), [pi-setup.md](pi-setup.md), [anomaly-detection.md](anomaly-detection.md), [../README.md](../README.md).

---

## 1. Purpose

**TerraMetric** is an IoT-based environmental monitoring (and optional control) stack for **indoor plant / GMO research**. It ties **sensor streams** to **named plant samples**, **recording sessions**, and **research-integrity** tooling (alerts, anomalies, reports) so experiments are **traceable** and **defensible**.

---

## 2. End-to-end architecture (one slide)

```
Arduino (sensors: DHT11, PIR, LDR, ultrasonic)
    │  JSON over Bluetooth / serial
    ▼
Raspberry Pi (optional)  →  pi/arduino_bridge.py  →  POST /api/telemetry/ingest
    │                                                    │
    │  (optional parallel path)                          ▼
    └→ Node-RED / ThingsBoard CE (live dashboards)    FastAPI backend + SQLite/Postgres
                                                           │
                                                           ▼
                                                    TerraMetric web UI (static + JS)
                                                    (same origin as /api when served by uvicorn)
```

**Why:** The **backend + database** is the **authoritative** store for the custom app, alerts, and session-scoped history. ThingsBoard/Node-RED are **optional** for extra live views; they are not required for the TerraMetric pages to work.

---

## 3. Web application (TerraMetric UI)

Served from `frontend/` when you run the FastAPI app with static files (`/` → `index.html`, plus `js/`, `css/`).

| Area | What it does | Why it matters |
|------|----------------|----------------|
| **Home** | Live stat cards, chart hooks, ESI/alert display paths | At-a-glance “is the chamber within expectations?” |
| **View Data → Graphs** | Time-series for temp/humidity/light/height; sample picker, time range, binning, optional “this session only” | **Exploratory analysis** and supervision of a run |
| **View Data → Gallery** | Growth photos keyed to plants / QR | **Visual** traceability alongside sensors |
| **View Data → Anomalies** | Live anomaly log + charts aligned with telemetry; **synthetic lab** (offline) for demos; optional **reprocess** | **Data-quality** and detector visibility without a second toolchain |
| **Control Variables** | Per-sample **thresholds** and **read intervals**; persisted via **plant control** profile API | **Document** intended conditions; feeds **server threshold alerts** |
| **Manage Samples** | CRUD for “tray”/plant records; **device registration**; **start/stop recording**; **dummy stream** / backfill for testing | Ties every row to a **plant** and a **session** for integrity |
| **Sign in** (`login.html`) | JWT session; protected APIs | **Multi-user** access with **per-user plant ownership** |
| **Admin registration** (`admin-register.html`) | Optional admin account creation (server-guarded) | Course/demo admin without a full user admin UI |

Configuration for API host/port: `frontend/js/config.js` (must match where **uvicorn** listens, e.g. port **8000**).

---

## 4. Backend API (what to name in technical slides)

Routers are registered in `backend/main.py`. Prefixes below are all under the same **base URL** as the app (e.g. `http://127.0.0.1:8000`).

| Area | Route prefix | Role |
|------|----------------|------|
| **Health** | `GET /health` | Liveness for demos and monitoring |
| **Auth** | `/api/auth` | Register, login, current user — **JWT** |
| **Admin** | `/api/admin` | Admin registration (policy/secret as implemented) |
| **Telemetry** | `/api/telemetry` | `latest`, `timeseries` (filters: plant, hours, binning, session), `ingest` |
| **Alerts** | `/api/alerts` | **Persisted** server alerts (e.g. threshold breaches) for UI bell/home |
| **Control** | `/api/control` | Get/update **per-plant** control profile JSON; reset path as implemented |
| **Camera** | `/api/camera` | Images for gallery / growth |
| **Plants** | `/api/plants` | **Sample/plant** CRUD — **scoped to owning user** |
| **Devices** | `/api/devices` | Register physical device (e.g. Bluetooth name) for recording |
| **Sessions** | `/api/sessions` | Start/stop **recording session**, list **active** sessions, dummy-stream metadata |
| **Reports** | `/api/reports` | **Integrity / research** reporting (FR11) |
| **Anomalies** | `/api/anomalies` | **Persisted** detector events; **synthetic** simulate; **reprocess** window |
| **Dummy** | `/api/dummy` | Dummy/backfill helpers for development |

OpenAPI: **`/docs`** on the same host (FastAPI auto-docs).

---

## 5. Functional requirements (FR1–FR12) — mapping

The README lists **functional requirements** (FR1–FR12). The codebase is organised around these themes:

| ID | Theme | Typical implementation home |
|----|--------|------------------------------|
| **FR1** | Environmental monitoring | Telemetry ingest + latest/sensor streams |
| **FR2** | Data logging & visualisation | `telemetry` + timeseries; charts on View Data |
| **FR3** | Alerts & early warning | `alerts` + threshold evaluation vs control profiles |
| **FR4** | Automated control | Control profiles, control API (setpoints/intervals as designed) |
| **FR5** | Camera / visual | `camera` + gallery |
| **FR6** | User & data management | Auth, JWT, per-user **plant** ownership |
| **FR7** | Plant / sample ID | `plants`, QR/fields, device linkage |
| **FR8** | Environmental Stability Index (ESI) | `esi_service` + home/telemetry integration |
| **FR9** | Cumulative stress | `stress_service` |
| **FR10** | Anomaly detection | `anomaly_service`, detectors, persisted events, API + UI |
| **FR11** | Session integrity report | `reports` |
| **FR12** | Time-in-tolerance visual overlay | As implemented in chart/threshold layer |

*Note: README may still list some FRs as “scaffold” — check latest code and tests for **current** depth.*

---

## 6. Anomaly detection (headline for one slide)

- **Online:** Detectors run as telemetry is **stored**; events persist per **plant** (and link to `telemetry` where applicable).  
- **API:** `GET /api/anomalies` returns events **for the current user’s plants** (query: plant, hours, session, etc.).  
- **Synthetic lab:** `POST /api/anomalies/simulate` for **offline** scenario runs (lab use; not a substitute for live history unless you explicitly design it that way).  
- **Reprocess:** `POST /api/anomalies/reprocess` to replay a **time window** after code changes or to backfill events.

Design detail: [anomaly-detection.md](anomaly-detection.md).

---

## 7. Edge & Pi (hardware demo)

- **Arduino** sketch: `arduino/arduino_bluetooth/` — JSON line format aligned with **ingest** schema.  
- **Bridge:** `pi/arduino_bridge.py` forwards serial/Bluetooth lines to `POST /api/telemetry/ingest`; base URL via **`TM_BRIDGE_API`** (default aligned with your backend port).  
- **Pi setup** (pairing, systemd, etc.): [pi-setup.md](pi-setup.md).

---

## 8. Suggested 5–10 minute demo script

1. **Health** — `GET /health` — “backend is up.”  
2. **Login** — show JWT-protected use of the app.  
3. **Manage Samples** — create/save a plant; register device if using hardware; **Start recording** (or enable dummy stream).  
4. **View Data** — show graphs; optional **this recording only**; mention binning.  
5. **Anomalies** — show persisted events; optionally run **synthetic lab** for a clear detector story.  
6. **Control** — show saved thresholds; relate to **alerts** if a breach is configured.  
7. **One sentence on integrity** — sessions + plant ownership + stored telemetry + reports/anomalies = **auditable** trial record.

---

## 9. Running locally (short)

| Step | Command / URL |
|------|----------------|
| Backend | `cd backend` → `python -m venv venv` → activate → `pip install -r requirements.txt` → `uvicorn main:app --host 127.0.0.1 --port 8000` |
| Or | Use repo root `run_dashboard.bat` (see file for port) |
| UI | Open **`http://127.0.0.1:8000/`** (or the port in `config.js`) — not `file://` |
| API docs | `http://127.0.0.1:8000/docs` |
| Vite (optional) | `cd frontend` → `npm install` → `npm run dev` (proxies `/api`; see [setup-guide.md](setup-guide.md)) |

---

## 10. Team file pointers (from README; update as your roles evolve)

| Area | Suggested code paths |
|------|----------------------|
| Anomalies / simulation | `backend/services/anomaly_service.py`, `simulation/`, `backend/api/anomalies.py` |
| Telemetry / ESI / stress | `backend/services/telemetry_service.py`, `esi_service.py`, `stress_service.py` |
| Alerts | `backend/api/alerts.py`, `services/alert_service.py` / `threshold_service.py` as applicable |
| Frontend (React) | `frontend/src/` (Vite app); static shell: `frontend/index.html` + `js/` |
| Reports | `backend/api/reports.py`, `services/report_service.py` |
| Control | `backend/api/control.py`, `services/plant_control_service.py` |
| Camera / plants | `backend/api/camera.py`, `services/camera_service.py`, `plant_service.py` |

---

*Document generated for team presentations. Update FR status and team table in [README.md](../README.md) as the project matures.*
