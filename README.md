# TerraMetric

A plant monitoring system for controlled greenhouse environments, built as a Cardiff University group project (CM2305, Group 14). It tracks temperature, humidity and light in real time, shows them on a live web dashboard and raises alerts when readings drift out of range.

> This is a team project. The "My contribution" section below says exactly which parts I (Osamah Eturki) built. Everything else was written by my teammates.

## What it does

- Reads temperature/humidity, motion and light sensors from an Arduino inside a 3D-printed greenhouse
- Sends the readings through a Raspberry Pi and Node-RED to a FastAPI backend that stores and serves them
- Shows live data on a web dashboard, with thresholds researchers can set per plant
- Turns sensor readings into a single 0-100 stability score (ESI) that non-technical users can read at a glance
- Lets researchers export their data as CSV for traceable evidence

## How the data flows

```
Arduino sensors -> Raspberry Pi -> Node-RED -> FastAPI backend -> Web dashboard
```

## My contribution

**Student:** Osamah Eturki

- **Web dashboard (HTML / CSS / JavaScript).** I built the single-page dashboard in `frontend/` (`index.html`, `js/`, `css/`): Home, View Data, Control Variables and Manage Samples pages.
  - Live telemetry chart that refreshes without a page reload
  - Stability score gauge for non-technical users
  - Per-sensor threshold controls with input validation
  - CSV export on the View Data page
  - A single `config.js` file is the only thing you edit to deploy it somewhere new. This made switching devices at short notice during the demo take about ten seconds.
- **Sensor wiring.** I wired the temperature/humidity, motion and light sensors to the Arduino inside the enclosure and tested each one before handing over to the backend team.
- **Risk register.** I wrote and presented the project risk register (hardware, software and team risks) for the funding pitch.
- **Pitch and demo.** I designed the 11 slides for the sales pitch, presented the deployment roadmap, and helped film and edit the demo video.

## Team

TerraMetric was built by Group 14 at Cardiff University: Omer Azhar, Harini Ramesh, Bo Song, Jena Charles, Christopher Thurman, Muhammad Azhar and Osamah Eturki.

Everything outside the parts listed in "My contribution" was built by my teammates. The commit history shows who wrote each part.

## Running it

You need Python 3.

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000/ . The backend serves the dashboard too. On Windows you can double-click `run_dashboard.bat` instead.

To point the dashboard at a different machine (for example the Raspberry Pi), edit `PI_IP` and `PORT` in `frontend/js/config.js`.

## What I would improve

- Automated UI tests. Testing the dashboard is currently manual, so a backend API change could break it unnoticed.
- Lazy-load the page fragments so they only load when you navigate to them, instead of all at startup.
- Agree API data formats in the first sprint. Late format mismatches between hardware, backend and frontend cost us time near the deadline.

## What I learned

Test wireless hardware (Bluetooth) in the very first session, agree data formats early, and build for how something will actually be used rather than just whether it works.
