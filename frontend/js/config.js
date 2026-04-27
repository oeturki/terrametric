//  TERRAMETRIC — CONFIGURATION
//  Set PI_IP and PORT to match where you run uvicorn (see run_dashboard.bat).
//  Default PORT is 8000 — same as: uvicorn main:app --reload

const CONFIG = {

  // ── Server IP address and port ─────────────────────────────
  PI_IP:  '127.0.0.1',   // e.g. '192.168.1.42'
  PORT:   8000,

  // ── How often to refresh data (milliseconds) ───────────────
  REFRESH_LIVE:   10000,  // stat cards  — every 10 seconds
  REFRESH_CHARTS: 30000,  // charts      — every 30 seconds
  REFRESH_ALERTS: 15000,  // alerts      — every 15 seconds

  // ── Default thresholds ─────────────────────────────
  //    (can also be changed live on the Control Variables page)
  DEFAULTS: {
    temp_min: 20,
    temp_max: 30,
    temp_warn_high: 50,  // high °C (soft, Home)
    temp_warn_low: 10,  // low °C 
    temp_int: 60,   // seconds
    hum_min: 20,
    hum_max: 40,
    hum_warn_high: 80,   // %
    hum_warn_low: 10,    // %
    hum_interval: 30, // seconds
    light_min: 5000,
    light_max: 10000,
    light_warn_high: 11000,  // lux
    light_warn_low: 3000,
    light_interval: 15, // seconds
    motion_min: 0,
    motion_max: 1,
    motion_interval: 10, // seconds
    height_min: 500,
    height_max: 10000,
    height_warn_high: 11000,   // cm
    height_warn_low: 100,
    height_interval: 120,   // seconds
    cam_on_motion: 0,
    cam_on_alert: 0,
    cam_interval: 60,  //change this-its not minutes
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
    alerts:    '/api/alerts/active',
    anomalies: '/api/anomalies',
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
      document.getElementById("warn-temp").value = data.temperature.warn ?? "";
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
      document.getElementById("warn-hum").value = data.humidity.warn ?? "";
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
      document.getElementById("warn-light").value = data.light.warn ?? "";
      document.getElementById("int-light").value = data.light.interval ?? "";
    }

    // Motion
    if (data.motion){
      document.getElementById("motion-min").value = data.motion.min ?? "";
      document.getElementById("motion-max").value = data.motion.max ?? "";
      document.getElementById("int-motion").value = data.motion.interval ?? "";
    }

    // Height
    if (data.height){
      document.getElementById("height-min").value = data.height.min ?? "";
      document.getElementById("height-max").value = data.height.max ?? "";
      const ywl = data.height.warn_low;
      const hLo = document.getElementById("warn-height-low");
      if (hLo) {
        hLo.value = ywl != null && ywl !== "" ? ywl : "";
      }
      document.getElementById("warn-height").value = data.height.warn ?? "";
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
      min: parseFloat(document.getElementById("motion-min").value),
      max: parseFloat(document.getElementById("motion-max").value),
      interval: parseInt(document.getElementById("int-motion").value, 10)
    },

    height: {
      min: parseFloat(document.getElementById("height-min").value),
      max: parseFloat(document.getElementById("height-max").value),
      warn_low: _optControlFloat("warn-height-low"),
      warn_high: _optControlFloat("warn-height-high"),
      interval: parseInt(document.getElementById("int-height").value, 10)
    },

    camera: (function () {
      const intEl = document.getElementById("int-cam");
      let minutes = 60;
      if (intEl) {
        if (intEl.tagName === "SELECT") {
          const m = { "1h": 60, "12h": 720, "24h": 1440, "1w": 10080, custom: 60 };
          minutes = m[intEl.value] != null ? m[intEl.value] : 60;
        } else {
          minutes = parseInt(intEl.value, 10) || 60;
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
  attachRangeValidation('height-min', 'height-max');
  attachRangeValidation('warn-temp-low', 'warn-temp-high');
  attachRangeValidation('warn-hum-low', 'warn-hum-high');
  attachRangeValidation('warn-light-low', 'warn-light-high');
  // attachRangeValidation('warn-motion-low', 'warn-motion'); #motion is either true or false, no threshold range
  attachRangeValidation('warn-height-low', 'warn-height-high');
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

  if (data.temperature.warn != null && !isNaN(data.temperature.warn) && data.temperature.warn > data.temperature.max) {
    alert("Temperature tolerance (high) cannot exceed desired max");
    return false;
  }
  if (data.temperature.warn_low != null && !isNaN(data.temperature.warn_low) && data.temperature.warn != null
      && !isNaN(data.temperature.warn) && data.temperature.warn_low >= data.temperature.warn) {
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

  const hW = data.humidity.warn;
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

  const lW = data.light.warn;
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

  // ── Motion ──
  if (isNaN(data.motion.min) || isNaN(data.motion.max)) {
    alert("Motion range must be numbers");
    return false;
  }
  if (data.motion.min >= data.motion.max) {
    alert("Motion min must be less than max");
    return false;
  }
  const mW = data.motion.warn;
  const mWl = data.motion.warn_low;
  if (mWl != null && !isNaN(mWl) && mW != null && !isNaN(mW) && mWl >= mW) {
    alert("Motion tolerance low must be less than tolerance high");
    return false;
  }
  if (mWl != null && !isNaN(mWl) && (mWl < 0 || mWl > 1)) {
    alert("Motion tolerance (low) must be between 0 and 1");
    return false;
  }
  if (mW != null && !isNaN(mW) && (mW < 0 || mW > 1)) {
    alert("Motion tolerance (high) must be between 0 and 1");
    return false;
  }

  // ── Height ──
  if (isNaN(data.height.min) || isNaN(data.height.max)) {
    alert("Height values must be numbers");
    return false;
  }

  if (data.height.min >= data.height.max) {
    alert("Height min must be less than max");
    return false;
  }
  const yW = data.height.warn;
  const yWl = data.height.warn_low;
  if (yWl != null && !isNaN(yWl) && yW != null && !isNaN(yW) && yWl >= yW) {
    alert("Height tolerance low must be less than tolerance high");
    return false;
  }

  // ── Camera ──
  if (isNaN(data.camera.interval) || data.camera.interval <= 0) {
    alert("Camera interval must be a positive number");
    return false;
  }

  // ── Motion (optional but good) ──
  if (isNaN(data.motion.interval) || data.motion.interval <= 0) {
    alert("Motion interval must be a positive number");
    return false;
  }

  return true;
}