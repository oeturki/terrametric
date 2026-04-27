# Raspberry Pi Setup (Arduino → TerraMetric)

This guide shows how to run the TerraMetric backend on a Raspberry Pi and
feed live Arduino + HC-05 Bluetooth telemetry into it.

End-to-end flow:

```
Arduino (DHT11 / PIR / LDR / HC-SR04)
  │  HC-05 Bluetooth Classic, JSON lines @ ~5 Hz
  ▼
Raspberry Pi
  /dev/rfcomm0  (rfcomm bind)
  │  pi/arduino_bridge.py  -> POST /api/telemetry/ingest
  ▼
FastAPI  (uvicorn main:app on port 8000)
  │  attaches row to the open recording session
  ▼
SQLite  +  Web UI at  http://<pi-ip>:8000/
```

The Arduino sketch in [`arduino/arduino_bluetooth/arduino_bluetooth.ino`](../arduino/arduino_bluetooth/arduino_bluetooth.ino)
already emits JSON lines whose keys match [`backend/schemas/ingest.py`](../backend/schemas/ingest.py),
so the bridge just has to ship each line to `/api/telemetry/ingest`.

---

## 1. Install prerequisites on the Pi

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git \
                    bluetooth bluez bluez-tools rfkill
```

Clone the repo (or copy it over) somewhere on the Pi, e.g. `/home/pi/group-14-cm2305-2211`.

## 2. Run the backend

```bash
cd /home/pi/group-14-cm2305-2211/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` so your laptop/phone on the same LAN can reach
`http://<pi-ip>:8000/`. The UI is served from `/`, the OpenAPI docs from `/docs`.

If you want the UI hosted from your laptop to talk to the Pi, edit
`frontend/js/config.js` so `PI_IP` matches the Pi's LAN IP. The default port
(`8000`) already matches the server.

Quick health check from the Pi itself:

```bash
curl -s http://127.0.0.1:8000/health
# -> {"status":"ok"}
```

## 3. Pair and bind the HC-05

HC-05 uses **Bluetooth Classic / SPP**, so we pair once and expose the link
as a virtual serial device.

```bash
sudo systemctl enable --now bluetooth
rfkill unblock bluetooth
bluetoothctl
```

Inside `bluetoothctl`:

```
power on
agent on
default-agent
scan on
# wait for the HC-05 to appear (name "Group14" from the sketch).
# Note its MAC, e.g. AA:BB:CC:DD:EE:FF
pair   AA:BB:CC:DD:EE:FF        # PIN is usually 1234 or 0000
trust  AA:BB:CC:DD:EE:FF
scan off
quit
```

Bind channel 1 (SPP) to `/dev/rfcomm0`:

```bash
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
ls -l /dev/rfcomm0
sudo usermod -aG dialout "$USER"   # then log out+in so you can open the port
```

Smoke test the link (Arduino must be powered, HC-05 LED should stop blinking
fast and pair solid):

```bash
stty -F /dev/rfcomm0 9600 -crtscts
cat /dev/rfcomm0
# You should see lines like:
# {"temperature":24.3,"humidity":58.0,"movement":false,"light":812,"distance":21}
```

If you don't see data, power-cycle the Arduino and re-open `cat` — HC-05 often
only connects the first time something opens the port.

## 4. Install bridge dependencies and run it

```bash
cd /home/pi/group-14-cm2305-2211
pip install pyserial requests          # add to the backend venv, or use system python
python pi/arduino_bridge.py
```

Expected output:

```
11:05:03 [bridge] INFO opening /dev/rfcomm0 @ 9600
11:05:03 [bridge] INFO connected; forwarding to http://127.0.0.1:8000/api/telemetry/ingest (bt_name=Group14)
11:05:18 [bridge] INFO health: ok=68 bad=2 in last 15s
```

Environment overrides (optional):

| Var                   | Default                  | Purpose                                             |
| --------------------- | ------------------------ | --------------------------------------------------- |
| `TM_BRIDGE_PORT`      | `/dev/rfcomm0`           | Serial device to read                               |
| `TM_BRIDGE_BAUD`      | `9600`                   | Must match the HC-05 (sketch uses 9600)             |
| `TM_BRIDGE_API`       | `http://127.0.0.1:8000`  | Backend base URL                                    |
| `TM_BRIDGE_BT_NAME`   | `Group14`                | Matches `AT+NAME` in the sketch + UI device record  |

## 5. Register the device and start recording (Web UI)

1. On your laptop open `http://<pi-ip>:8000/`.
2. Go to **Manage Samples** → select / save a sample so it has a server ID.
3. In *Register new device* fill:
   - **Bluetooth name**: `Group14` (exact match — case-sensitive)
   - **Display label**: any, e.g. "Chamber Arduino"
   - **MAC address**: optional
4. Click **Register device**, then pick it in the *Arduino / device* dropdown.
5. **Uncheck** *Stream dummy data while recording* (we want the real device).
6. Click **Start recording**.
7. Switch to **View Data → Graphs**. Your sample should already be selected
   (the UI syncs to the active recording); you'll see the green session hint
   "Live device · session #N · scenario 'stable'". Tick **This recording only**
   to hide any older backfill rows.

## 6. End-to-end sanity test without the Arduino

Pretend to be the bridge with `curl`:

```bash
curl -s -X POST http://127.0.0.1:8000/api/telemetry/ingest \
  -H 'Content-Type: application/json' \
  -d '{"temperature":24.3,"humidity":58,"movement":false,"light":812,"distance":21,"bt_name":"Group14"}'
```

- Recording active for the sample linked to `Group14`:
  `{"stored":true,"session_id":<id>,"message":null}`
- No recording active: `{"stored":true,"session_id":null,"message":"no_active_recording_session"}`
  (row is still stored, just without a session/plant tag).

## 7. Optional: autostart on boot via systemd

Three units, all in `/etc/systemd/system/`:

**`rfcomm-arduino.service`** — recreates `/dev/rfcomm0` after reboot:

```ini
[Unit]
Description=Bind HC-05 Arduino to /dev/rfcomm0
After=bluetooth.service
Requires=bluetooth.service

[Service]
ExecStart=/usr/bin/rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
ExecStop=/usr/bin/rfcomm release 0
RemainAfterExit=yes
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**`terrametric.service`** — the backend:

```ini
[Unit]
Description=TerraMetric backend (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/group-14-cm2305-2211/backend
ExecStart=/home/pi/group-14-cm2305-2211/backend/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**`arduino-bridge.service`** — the serial→HTTP pump:

```ini
[Unit]
Description=Arduino -> TerraMetric bridge
After=terrametric.service rfcomm-arduino.service
Requires=terrametric.service rfcomm-arduino.service

[Service]
User=pi
WorkingDirectory=/home/pi/group-14-cm2305-2211
ExecStart=/home/pi/group-14-cm2305-2211/backend/.venv/bin/python pi/arduino_bridge.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rfcomm-arduino.service terrametric.service arduino-bridge.service
journalctl -u arduino-bridge -f
```

## 8. Troubleshooting

| Symptom                                                    | Fix                                                                                                              |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `/dev/rfcomm0: No such file or directory`                  | Re-run `sudo rfcomm bind 0 AA:BB:... 1`; install `rfcomm-arduino.service` to auto-rebind on boot.                |
| `Permission denied` opening `/dev/rfcomm0`                 | Add your user to `dialout` (`sudo usermod -aG dialout "$USER"`) and re-login, or `sudo chmod 666 /dev/rfcomm0`.  |
| Bridge logs `bad=…` and no `ok`                            | The Arduino is printing debug text, not JSON. Confirm with `cat /dev/rfcomm0`. Reflash the provided sketch.      |
| Ingest returns `no_active_recording_session`               | Start a recording in Manage Samples. Rows are still stored; they just aren't attached to a sample.               |
| Graphs stay empty                                          | On View Data, pick the correct sample; untick **This recording only** to include older/backfill rows.            |
| HC-05 connects once then drops                             | Many HC-05 clones hate RF interference / low USB power. Use a 2.4 GHz-safe spot and a quality Pi PSU.            |
| BLE module instead of HC-05                                | This guide is for HC-05 Classic. BLE needs a different GATT-based bridge — out of scope here.                     |
