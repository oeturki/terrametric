// ╔══════════════════════════════════════════════════════════════╗
//  TERRAMETRIC — CONFIGURATION
//  ← The ONLY file you and your teammates need to edit ←
// ╠══════════════════════════════════════════════════════════════╣
//
//  Set PI_IP below to your server's IP address
//  then make sure the server is running.
//
// ╚══════════════════════════════════════════════════════════════╝

const CONFIG = {

  // ── Server IP address and port ─────────────────────────────
  PI_IP:  '127.0.0.1',   // e.g. '192.168.1.42'
  PORT:   8000,

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

// Derived base URL — do not edit
const API_BASE = `http://${CONFIG.PI_IP}:${CONFIG.PORT}`;
