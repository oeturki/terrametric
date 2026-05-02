# Laptop smoke test (single command)

**Start the stack** — run the launcher **from inside** the **`backend`** folder (same place as `.env` and `requirements.txt`):

- Double-click **`start_terrametric_laptop.bat`** in that folder in Explorer, **or**:

```bat
cd path\to\group-14-cm2305-2211\backend
start_terrametric_laptop.bat
```

Avoid `cmd /c start_terrametric_laptop.bat` **unless your current folder is already `backend`** (wrong directory → `.env`/paths broken). PowerShell:

```powershell
cd path\to\group-14-cm2305-2211\backend
.\start_terrametric_laptop.bat
```

The script **`start_terrametric_laptop.ps1`** will:

1. Ensure **`backend\.env`** exists (copies from example the first time).
2. Create **`backend\venv`** if missing, then **`pip install -r requirements.txt`** every launch (keeps deps in sync — including `joblib` / sklearn).

Then open a browser on the **same PC**.

---

## 1. Automated readiness (no login)

| URL | What you want |
|-----|----------------|
| http://127.0.0.1:8000/health | `{"status":"ok"}` |
| http://127.0.0.1:8000/api/health/ready | JSON with `overall_ok: true` when DB + ML libs + (if ML enabled) model load work |

Swagger (optional): http://127.0.0.1:8000/docs

---

## 2. Full UI (everything in one app origin)

| Step | Where in the UI |
|------|-----------------|
| Log in | http://127.0.0.1:8000/login.html |
| Dashboard / home | http://127.0.0.1:8000/ or **Home** in the sidebar |
| Telemetry charts | **View Data → Graphs** — pick sample + range, **Refresh**. |
| Anomalies + rule events | **View Data → Anomalies** — same sample; events from DB. |
| **ML classify (stored rows)** | **View Data → Anomalies** → **ML pass** hours + **Run ML scan**. |
| Samples / recordings | **Manage Samples** |
| Dummy / backfill | **Manage Samples** (if used) |
| Control / hardware | **Control Variables** |

Everything is served from **`http://127.0.0.1:8000`** — no `npm run dev` needed for this HTML UI.

---

## 3. If something fails

- **`/api/health/ready`** lists what is `false` — fix those (`database`, `joblib`, `sklearn`, `ml_model_file`, etc.).
- **401**: log in at `login.html` so JWT is stored.
- **Empty charts**: add telemetry for that plant/window.

---

## 4. Automated tests (optional, dev)

From **repo root**:

```bash
python -m pytest tests/ -q
```
