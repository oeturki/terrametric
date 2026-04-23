//  TERRAMETRIC — CONFIGURATION
//  Set PI_IP and PORT to match where you run uvicorn (see run_dashboard.bat).
//  Default PORT is 8765 so it does not clash with other apps using 8000.

const CONFIG = {

  // ── Server IP address and port ─────────────────────────────
  PI_IP:  '127.0.0.1',   // e.g. '192.168.1.42'
  PORT:   8765,          // local dev (run_dashboard.bat); use 8000 on Pi if needed

  // ── How often to refresh data (milliseconds) ───────────────
  REFRESH_LIVE:   10000,  // stat cards  — every 10 seconds
  REFRESH_CHARTS: 30000,  // charts      — every 30 seconds
  REFRESH_ALERTS: 15000,  // alerts      — every 15 seconds

  // ── Default thresholds ─────────────────────────────
  //    (can also be changed live on the Control Variables page)
  DEFAULTS: {
    temp_min:         15,
    temp_max:         30,
    temp_warn:         5,   // °C
    temp_int:         60,   // seconds
    hum_min:          20,
    hum_max:          40,
    hum_warn:          5,   // %
    hum_interval:     60, // seconds
    light_min:      5000,
    light_max:     10000,
    light_warn:      500,  // lux
    light_interval:   60, // seconds
    motion_min:        0,
    motion_max:        1,
    motion_warn:       1,
    motion_interval:  20, // seconds
    height_min:        0,
    height_max:    10000,
    height_warn:       5,   // cm
    height_interval:1440,   // minutes
    cam_on_motion:     0,
    cam_on_alert:      0,
    cam_interval:     60,  // minutes
  },

  // ── API endpoint paths ─────────────────────────────────────
  //    Only change these if your server uses different route names
  ENDPOINTS: {
    health:    '/health',
    latest:    '/api/telemetry/latest',
    telemetry: '/api/telemetry/timeseries',
    alerts:    '/api/alerts/active',
    anomalies: '/api/anomalies',
    plants:    '/api/plants',
    control:   '/api/control',
    camera:    '/api/camera/images',
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
// Expected JSON: { group, temp_warn, temp_interval, hum_warn, hum_interval, … }

async function fetchControls() { //use this one
  const group = document.getElementById("groupSelect").value;

  try {
    const res = await fetch(`${API_BASE}${CONFIG.ENDPOINTS.control}?group=${group}`);
    if (!res.ok) {
      console.error("Failed to load controls");
      return;
    }
    const data = await res.json();

    // Temperature
    if (data.temperature){
      document.getElementById("temp-min").value = data.temperature.min ?? "";
      document.getElementById("temp-max").value = data.temperature.max ?? "";
      document.getElementById("warn-temp").value = data.temperature.warn ?? "";
      document.getElementById("int-temp").value = data.temperature.interval ?? "";
    }

    // Humidity
    if (data.humidity){
      document.getElementById("humid-min").value = data.humidity.min ?? "";
      document.getElementById("humid-max").value = data.humidity.max ?? "";
      document.getElementById("warn-hum").value = data.humidity.warn ?? "";
      document.getElementById("int-hum").value = data.humidity.interval ?? "";
    }

    // Light
    if (data.light){
      document.getElementById("light-min").value = data.light.min ?? "";
      document.getElementById("light-max").value = data.light.max ?? "";
      document.getElementById("warn-light").value = data.light.warn ?? "";
      document.getElementById("int-light").value = data.light.interval ?? "";
    }

    // Motion
    if (data.motion){
      document.getElementById("motion-min").value = data.motion.min ?? "";
      document.getElementById("motion-max").value = data.motion.max ?? "";
      document.getElementById("warn-motion").value = data.motion.warn ?? "";
      document.getElementById("int-motion").value = data.motion.interval ?? "";
    }

    // Height
    if (data.height){
      document.getElementById("height-min").value = data.height.min ?? "";
      document.getElementById("height-max").value = data.height.max ?? "";
      document.getElementById("warn-height").value = data.height.warn ?? "";
      document.getElementById("int-height").value = data.height.interval ?? "";
    }

    // Camera
    if (data.camera){
      document.getElementById("cam-on-motion").checked = !!data.camera.on_motion;
      document.getElementById("cam-on-alert").checked = !!data.camera.on_alert;
      document.getElementById("int-cam").value = data.camera.interval ?? "";
    }

  } catch (err) {
    console.error(err);
  }
}

function getControlData() {
  return {
    group: document.getElementById("groupSelect").value,

    temperature: {
      min: parseFloat(document.getElementById("temp-min").value),
      max: parseFloat(document.getElementById("temp-max").value),
      warn: parseFloat(document.getElementById("warn-temp").value),
      interval: parseInt(document.getElementById("int-temp").value, 10)
    },

    humidity: {
      min: parseFloat(document.getElementById("humid-min").value),
      max: parseFloat(document.getElementById("humid-max").value),
      warn: parseFloat(document.getElementById("warn-hum").value),
      interval: parseInt(document.getElementById("int-hum").value, 10)
    },

    light: {
      min: parseFloat(document.getElementById("light-min").value),
      max: parseFloat(document.getElementById("light-max").value),
      warn: parseFloat(document.getElementById("warn-light").value),
      interval: parseInt(document.getElementById("int-light").value, 10)
    },

    motion: {
      min: parseFloat(document.getElementById("motion-min").value),
      max: parseFloat(document.getElementById("motion-max").value),
      warn: parseFloat(document.getElementById("warn-motion").value),
      interval: parseInt(document.getElementById("int-motion").value, 10)
    },

    height: {
      min: parseFloat(document.getElementById("height-min").value),
      max: parseFloat(document.getElementById("height-max").value),
      warn: parseFloat(document.getElementById("warn-height").value),
      interval: parseInt(document.getElementById("int-height").value, 10)
    },

    camera: {
      on_motion: document.getElementById("cam-on-motion").checked,
      on_alert: document.getElementById("cam-on-alert").checked,
      interval: parseInt(document.getElementById("int-cam").value, 10)
    }
  };
}
  
async function saveControls() {
  const data = getControlData();

  if (!validateControls(data)) return;

  try {
    const res = await fetch(`${API_BASE}${CONFIG.ENDPOINTS.control}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(data)
    });

    const result = await res.json();

    if (!res.ok) {
      fireAlert('warning', 'Save Failed', result.error || 'Server error', 5000);
      return;
    }
    applyControlsToUI(result.controls);

    fireAlert('ok', 'Saved', 'Settings updated successfully', 4000);

  } catch (err) {
    console.error(err);
    fireAlert('warning', 'Connection Error', 'Could not reach server', 5000);
  }
}

async function resetControls() {
  const group = document.getElementById("groupSelect").value;

  try {
    const res = await fetch(`${API_BASE}/api/control/reset`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ group })
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
document.addEventListener('DOMContentLoaded', async () => {
  await fetchControls();
  attachRangeValidation('temp-min', 'temp-max');
  attachRangeValidation('humid-min', 'humid-max');
  attachRangeValidation('light-min', 'light-max');
  attachRangeValidation('height-min', 'height-max');
});

function validateControls(data) {

  // ── Temperature ──
  if (isNaN(data.temperature.min) || isNaN(data.temperature.max)) {
    alert("Temperature values must be numbers");
    return false;
  }

  if (data.temperature.min >= data.temperature.max) {
    alert("Temperature min must be less than max");
    return false;
  }

  if (data.temperature.warn > data.temperature.max) {
    alert("Temperature warning cannot exceed max");
    return false;
  }

  // ── Humidity ──
  if (isNaN(data.humidity.min) || isNaN(data.humidity.max)) {
    alert("Humidity values must be numbers");
    return false;
  }

  if (data.humidity.min < 0 || data.humidity.max > 100) {
    alert("Humidity must be between 0 and 100");
    return false;
  }

  if (data.humidity.warn > 100) {
    alert("Humidity warning cannot exceed 100%");
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

  // ── Height ──
  if (isNaN(data.height.min) || isNaN(data.height.max)) {
    alert("Height values must be numbers");
    return false;
  }

  if (data.height.min >= data.height.max) {
    alert("Height min must be less than max");
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