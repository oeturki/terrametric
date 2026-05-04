//  TERRAMETRIC — CONFIGURATION
//  Set PI_IP and PORT to match where you run uvicorn (see run_dashboard.bat).
//  Default PORT is 8000 — same as: uvicorn main:app --reload

const CONFIG = {

  // ── Server IP address and port ─────────────────────────────
  PI_IP:  '127.0.0.1',   // Same machine: 127.0.0.1. From another device on LAN use '10.3.25.73' (bench laptop)
  PORT:   8000,

  // ── How often to refresh data (milliseconds) ───────────────
  REFRESH_LIVE:   10000,  // stat cards  — every 10 seconds
  REFRESH_CHARTS: 30000,  // charts      — every 30 seconds
  REFRESH_ALERTS: 15000,  // alerts      — every 15 seconds

  // ── Default thresholds ─────────────────────────────
  //    (can also be changed live on the Control Variables page)
  DEFAULTS: {
    temp_min: 18,
    temp_max: 26,
    temp_warn_low: 16,
    temp_warn_high: 28,
    temp_int: 120,
    hum_min: 40,
    hum_max: 60,
    hum_warn_low: 35,
    hum_warn_high: 68,
    hum_interval: 120,
    light_min: 200,
    light_max: 2500,
    light_warn_low: 120,
    light_warn_high: 3200,
    light_interval: 120,
    motion_interval: 60,
    height_interval: 1440,
    cam_on_motion: 1,
    cam_on_alert: 1,
    cam_interval: 60,
  },

  // ── API endpoint paths ─────────────────────────────────────
  //    Only change these if your server uses different route names
  ENDPOINTS: {
    login:     '/api/auth/login',
    register:  '/api/auth/register',
    me:        '/api/auth/me',
    health:    '/health',
    latest:    '/api/telemetry/latest',
    telemetry: '/api/telemetry/timeseries',
    alerts:         '/api/alerts/active',
    /** POST with JSON `{}`. Use as `CONFIG.ENDPOINTS.alertsAck(alertId)`. */
    alertsAck: function (alertId) {
      return '/api/alerts/' + encodeURIComponent(String(alertId)) + '/ack';
    },
    /** POST JSON body `{ ids: number[] }` — marks alerts acknowledged (server-backed dismiss). */
    alertsAckBatch: '/api/alerts/ack-batch',
    anomalies: '/api/anomalies',
    mlClassifyWindow: '/api/ml/classify/window',
    plants:    '/api/plants',
    devices:   '/api/devices',
    sessionsActive: '/api/sessions/active',
    sessionsStart:  '/api/sessions/start',
    dummyBackfill:  '/api/dummy/backfill',
    control:   '/api/control',
    camera:    '/api/camera/images',
    hardwareCapture:   '/api/hardware/capture',
    hardwareVentilation: '/api/hardware/ventilation',
  },
};

// API base: same host+port as this page when it matches CONFIG (e.g. uvicorn serves UI + API);
// otherwise use CONFIG (e.g. UI on :8080, API still on CONFIG.PORT).
const API_BASE = (function () {
  const fromConfig = function () {
    return 'http://' + CONFIG.PI_IP + ':' + CONFIG.PORT;
  };
  if (typeof window === 'undefined' || !window.location.protocol.startsWith('http')) {
    return fromConfig();
  }
  var pagePort = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
  var cfgPort = String(CONFIG.PORT);
  var host = window.location.hostname;
  var hostMatches = host === CONFIG.PI_IP ||
    (CONFIG.PI_IP === '127.0.0.1' && host === 'localhost') ||
    (CONFIG.PI_IP === 'localhost' && host === '127.0.0.1');
  if (hostMatches && pagePort === cfgPort) {
    return window.location.origin;
  }
  return fromConfig();
})();

// ── Controls ─────────────────────────────────────────────────
// Per-plant contract: { plant_id, temperature, humidity, … } — same keys server stores.

const TERRAMETRIC_CONTROL_PLANT_KEY = "terrametric_control_plant_id";

/** Fill #groupSelect with server plants (sample list). Call after /api/plants load or samples:changed. */
function buildControlPlantSelectFromList(plants) {
  const sel = document.getElementById("groupSelect");
  if (!sel) return;
  const had = sel.value;
  const saved = localStorage.getItem(TERRAMETRIC_CONTROL_PLANT_KEY);
  sel.innerHTML = "";
  if (!plants || !plants.length) {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = "No samples — add one in Manage Samples";
    sel.appendChild(o);
    return;
  }
  plants.forEach(function (p) {
    const o = document.createElement("option");
    o.value = String(p.id);
    o.textContent = p.name ? p.name : "Plant #" + p.id;
    sel.appendChild(o);
  });
  const idSet = {};
  plants.forEach(function (p) { idSet[String(p.id)] = true; });
  let pick = (saved && idSet[saved]) ? saved : String(plants[0].id);
  if (had && idSet[had]) pick = had;
  sel.value = pick;
  localStorage.setItem(TERRAMETRIC_CONTROL_PLANT_KEY, pick);
}

async function fetchControls() {
  const sel = document.getElementById("groupSelect");
  const plantId = sel && sel.value;
  if (!plantId) {
    return;
  }
  localStorage.setItem(TERRAMETRIC_CONTROL_PLANT_KEY, plantId);

  try {
    const res = await authFetch(
      API_BASE + CONFIG.ENDPOINTS.control + "?plant_id=" + encodeURIComponent(plantId)
    );
    if (!res.ok) {
      console.error("Failed to load controls");
      return;
    }
    const data = await res.json();

    // Temperature
    if (data.temperature){
      document.getElementById("temp-min").value = data.temperature.min ?? "";
      document.getElementById("temp-max").value = data.temperature.max ?? "";
      const wlo = data.temperature.warn_low;
      const loEl = document.getElementById("warn-temp-low");
      if (loEl) {
        loEl.value = wlo != null && wlo !== "" ? wlo : "";
      }
      const wHi = data.temperature.warn_high != null && data.temperature.warn_high !== ""
        ? data.temperature.warn_high
        : data.temperature.warn;
      const hiEl = document.getElementById("warn-temp-high");
      if (hiEl) {
        hiEl.value = wHi != null && wHi !== "" ? wHi : "";
      }
      document.getElementById("int-temp").value = data.temperature.interval ?? "";
    }

    // Humidity
    if (data.humidity){
      document.getElementById("humid-min").value = data.humidity.min ?? "";
      document.getElementById("humid-max").value = data.humidity.max ?? "";
      const hwl = data.humidity.warn_low;
      const humLo = document.getElementById("warn-hum-low");
      if (humLo) {
        humLo.value = hwl != null && hwl !== "" ? hwl : "";
      }
      const hwHi = data.humidity.warn_high != null && data.humidity.warn_high !== ""
        ? data.humidity.warn_high
        : data.humidity.warn;
      const humHi = document.getElementById("warn-hum-high");
      if (humHi) {
        humHi.value = hwHi != null && hwHi !== "" ? hwHi : "";
      }
      document.getElementById("int-hum").value = data.humidity.interval ?? "";
    }

    // Light
    if (data.light){
      document.getElementById("light-min").value = data.light.min ?? "";
      document.getElementById("light-max").value = data.light.max ?? "";
      const lwl = data.light.warn_low;
      const lLo = document.getElementById("warn-light-low");
      if (lLo) {
        lLo.value = lwl != null && lwl !== "" ? lwl : "";
      }
      const lwHi = data.light.warn_high != null && data.light.warn_high !== ""
        ? data.light.warn_high
        : data.light.warn;
      const lightHi = document.getElementById("warn-light-high");
      if (lightHi) {
        lightHi.value = lwHi != null && lwHi !== "" ? lwHi : "";
      }
      document.getElementById("int-light").value = data.light.interval ?? "";
    }

    // Motion — interval only (PIR binary; no desired/tolerance persisted)
    if (data.motion){
      document.getElementById("int-motion").value = data.motion.interval ?? "";
    }

    // Height — optional goal only (stored as target_cm)
    if (data.height){
      const htEl = document.getElementById("height-target");
      if (htEl) {
        const tg = data.height.target_cm;
        htEl.value = tg != null && tg !== "" ? tg : "";
      }
      document.getElementById("int-height").value = data.height.interval ?? "";
    }

    // Camera — supports both <select> (index.html) and plain input variants.
    if (data.camera){
      const mEl = document.getElementById("cam-on-motion");
      const aEl = document.getElementById("cam-on-alert");
      if (mEl) mEl.checked = !!data.camera.on_motion;
      if (aEl) aEl.checked = !!data.camera.on_alert;
      const intEl = document.getElementById("int-cam");
      if (intEl) {
        const mins = Number(data.camera.interval);
        if (intEl.tagName === "SELECT" && !isNaN(mins)) {
          const rev = { 60: "1h", 720: "12h", 1440: "24h", 10080: "1w" };
          intEl.value = rev[mins] != null ? rev[mins] : "1h";
        } else {
          intEl.value = data.camera.interval != null ? String(data.camera.interval) : "";
        }
      }
    }

  } catch (err) {
    console.error(err);
  }
}

/** Optional numeric from control input: empty / invalid -> null (same as temperature). */
function _optControlFloat(id) {
  const el = document.getElementById(id);
  if (!el || el.value === "") {
    return null;
  }
  const x = parseFloat(el.value);
  return isNaN(x) ? null : x;
}

function getControlData() {
  const sel = document.getElementById("groupSelect");
  const plantId = sel && sel.value ? parseInt(sel.value, 10) : NaN;
  if (isNaN(plantId)) {
    return null;
  }
  return {
    plant_id: plantId,

    temperature: {
      min: parseFloat(document.getElementById("temp-min").value),
      max: parseFloat(document.getElementById("temp-max").value),
      warn_low: _optControlFloat("warn-temp-low"),
      warn_high: _optControlFloat("warn-temp-high"),
      interval: parseInt(document.getElementById("int-temp").value, 10)
    },

    humidity: {
      min: parseFloat(document.getElementById("humid-min").value),
      max: parseFloat(document.getElementById("humid-max").value),
      warn_low: _optControlFloat("warn-hum-low"),
      warn_high: _optControlFloat("warn-hum-high"),
      interval: parseInt(document.getElementById("int-hum").value, 10)
    },

    light: {
      min: parseFloat(document.getElementById("light-min").value),
      max: parseFloat(document.getElementById("light-max").value),
      warn_low: _optControlFloat("warn-light-low"),
      warn_high: _optControlFloat("warn-light-high"),
      interval: parseInt(document.getElementById("int-light").value, 10)
    },

    motion: {
      interval: parseInt(document.getElementById("int-motion").value, 10)
    },

    height: {
      target_cm: _optControlFloat("height-target"),
      interval: parseInt(document.getElementById("int-height").value, 10)
    },

    camera: (function () {
      const intEl = document.getElementById("int-cam");
      let minutes = 60;
      if (intEl) {
        if (intEl.tagName === "SELECT") {
          const m = { "1h": 60, "12h": 720, "24h": 1440, "1w": 10080};
          minutes = m[intEl.value] != null ? m[intEl.value] : 60;
        } else {
          minutes = parseInt(intEl.value, 10) || 60; //default to 60 otherwise use map
        }
      }
      const motion = document.getElementById("cam-on-motion");
      const alertEl = document.getElementById("cam-on-alert");
      return {
        on_motion: motion ? motion.checked : false,
        on_alert: alertEl ? alertEl.checked : false,
        interval: minutes,
      };
    })()
  };
}
  
async function saveControls() {
  const data = getControlData();
  if (!data) {
    fireAlert("warning", "No sample", "Add a sample in Manage Samples first.", 5000);
    return;
  }

  if (!validateControls(data)) return;

  try {
    const res = await authFetch(`${API_BASE}${CONFIG.ENDPOINTS.control}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(data)
    });

    const result = await res.json();

    if (!res.ok) {
      const d = result.detail;
      const msg = typeof d === "string" ? d : (Array.isArray(d) && d[0] && d[0].msg) || "Server error";
      fireAlert("warning", "Save Failed", msg, 5000);
      return;
    }
    await fetchControls();

    fireAlert("ok", "Saved", "Settings updated successfully", 4000);

  } catch (err) {
    console.error(err);
    fireAlert('warning', 'Connection Error', 'Could not reach server', 5000);
  }
}

async function resetControls() {
  const plantId = document.getElementById("groupSelect").value;
  if (!plantId) {
    fireAlert("warning", "No sample", "Add a sample in Manage Samples first.", 5000);
    return;
  }

  try {
    const res = await authFetch(`${API_BASE}/api/control/reset`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ plant_id: parseInt(plantId, 10) })
    });
    
    const result = await res.json();

    if (!res.ok) {
      alert(result.error || "Reset failed");
      return;
    }

    await fetchControls(); // reload UI

    alert("Reset to defaults!");
  } catch (err) {
    console.error(err);
    alert("Reset failed");
  }
}

function cancelChanges() {
  fetchControls(); // reload last saved values from backend
  fireAlert('info', 'Changes Discarded', 'Reverted to last saved settings.', 3000);
}

// ── Range Validation ─────────────────────────────────────────
function attachRangeValidation(minId, maxId) {
  const minInput = document.getElementById(minId);
  const maxInput = document.getElementById(maxId);

  if (!minInput || !maxInput) return;

  function validate() {
    const min = parseFloat(minInput.value);
    const max = parseFloat(maxInput.value);

    // ignore empty/invalid input
    if (isNaN(min) || isNaN(max)) return;

    // swap if user enters invalid range
    if (min > max) {
      [minInput.value, maxInput.value] = [maxInput.value, minInput.value];
    }
  }

  minInput.addEventListener('input', validate);
  maxInput.addEventListener('input', validate);
}
// run after page loads
document.addEventListener("DOMContentLoaded", async function () {
  if (document.getElementById("groupSelect") && document.getElementById("groupSelect").value) {
    await fetchControls();
  }
  attachRangeValidation('temp-min', 'temp-max');
  attachRangeValidation('humid-min', 'humid-max');
  attachRangeValidation('light-min', 'light-max');
  attachRangeValidation('warn-temp-low', 'warn-temp-high');
  attachRangeValidation('warn-hum-low', 'warn-hum-high');
  attachRangeValidation('warn-light-low', 'warn-light-high');
});

function validateControls(data) {
  if (!data || !data.plant_id) {
    alert("Select a sample first");
    return false;
  }

  // ── Temperature ──
  if (isNaN(data.temperature.min) || isNaN(data.temperature.max)) {
    alert("Temperature values must be numbers");
    return false;
  }

  if (data.temperature.min >= data.temperature.max) {
    alert("Temperature min must be less than max");
    return false;
  }

  const tWl = data.temperature.warn_low;
  const tWh = data.temperature.warn_high != null ? data.temperature.warn_high : data.temperature.warn;

  if (tWl != null && !isNaN(tWl) && tWh != null
      && !isNaN(tWh) && tWl >= tWh) {
    alert("Temperature tolerance low must be less than tolerance high");
    return false;
  }

  // ── Humidity ──
  if (isNaN(data.humidity.min) || isNaN(data.humidity.max)) {
    alert("Humidity values must be numbers");
    return false;
  }

  if (data.humidity.min >= data.humidity.max) {
    alert("Humidity min must be less than max");
    return false;
  }

  if (data.humidity.min < 0 || data.humidity.max > 100) {
    alert("Humidity must be between 0 and 100");
    return false;
  }

  const hW = data.humidity.warn_high != null ? data.humidity.warn_high : data.humidity.warn;
  const hWl = data.humidity.warn_low;
  if (hW != null && !isNaN(hW) && (hW > 100 || hW < 0)) {
    alert("Humidity tolerance (high) must be between 0 and 100%");
    return false;
  }
  if (hWl != null && !isNaN(hWl) && (hWl > 100 || hWl < 0)) {
    alert("Humidity tolerance (low) must be between 0 and 100%");
    return false;
  }
  if (hWl != null && !isNaN(hWl) && hW != null && !isNaN(hW) && hWl >= hW) {
    alert("Humidity tolerance low must be less than tolerance high");
    return false;
  }

  // ── Light ──
  if (isNaN(data.light.min) || isNaN(data.light.max)) {
    alert("Light values must be numbers");
    return false;
  }

  if (data.light.min >= data.light.max) {
    alert("Light min must be less than max");
    return false;
  }

  const lW = data.light.warn_high != null ? data.light.warn_high : data.light.warn;
  const lWl = data.light.warn_low;
  if (lW != null && !isNaN(lW) && lW < 0) {
    alert("Light tolerance (high) cannot be negative");
    return false;
  }
  if (lWl != null && !isNaN(lWl) && lWl < 0) {
    alert("Light tolerance (low) cannot be negative");
    return false;
  }
  if (lWl != null && !isNaN(lWl) && lW != null && !isNaN(lW) && lWl >= lW) {
    alert("Light tolerance low must be less than tolerance high");
    return false;
  }

  // ── Motion (interval only) ──
  if (isNaN(data.motion.interval) || data.motion.interval <= 0) {
    alert("Motion interval must be a positive number");
    return false;
  }

  // ── Height (optional desired height milestone) ──
  if (data.height.target_cm != null && !isNaN(data.height.target_cm) && data.height.target_cm <= 0) {
    alert("Desired height must be a positive number or left empty");
    return false;
  }
  if (isNaN(data.height.interval) || data.height.interval <= 0) {
    alert("Height read interval must be a positive number");
    return false;
  }

  // ── Camera ──
  if (isNaN(data.camera.interval) || data.camera.interval <= 0) {
    alert("Camera interval must be a positive number");
    return false;
  }

  return true;
}