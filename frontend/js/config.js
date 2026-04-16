// ╔══════════════════════════════════════════════════════════════╗
//  TERRAMETRIC — CONFIGURATION
//  ← The ONLY file you and your teammates need to edit ←
// ╠══════════════════════════════════════════════════════════════╣
//
//  Set PI_IP and PORT to match where you run uvicorn (see run_dashboard.bat).
//  Default PORT is 8765 so it does not clash with other apps using 8000.
//
// ╚══════════════════════════════════════════════════════════════╝

const CONFIG = {

  // ── Server IP address and port ─────────────────────────────
  PI_IP:  '127.0.0.1',   // e.g. '192.168.1.42'
  PORT:   8765,          // local dev (run_dashboard.bat); use 8000 on Pi if needed

  // ── How often to refresh data (milliseconds) ───────────────
  REFRESH_LIVE:   10000,  // stat cards  — every 10 seconds
  REFRESH_CHARTS: 30000,  // charts      — every 30 seconds
  REFRESH_ALERTS: 15000,  // alerts      — every 15 seconds

  // ── Default warning thresholds ─────────────────────────────
  //    (can also be changed live on the Control Variables page)
  DEFAULTS: {
    temp_warn:        28,   // °C
    hum_warn:         80,   // %
    light_warn:       200,  // lux
    height_warn:      35,   // cm
    temp_interval:    30,   // seconds
    hum_interval:     30,
    light_interval:   15,
    motion_interval:  10,
    height_interval:  120,
    cam_schedule:     '08:00, 14:00, 20:00',
    cam_interval:     360,  // minutes
  },

  // ── API endpoint paths ─────────────────────────────────────
  //    Only change these if your server uses different route names
  ENDPOINTS: {
    health:    '/health',
    latest:    '/api/telemetry/latest',
    telemetry: '/api/telemetry',
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
