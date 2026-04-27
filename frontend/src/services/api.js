/**
 * HTTP client for communicating with the Python backend API.
 */

import axios from "axios";

const api = axios.create({
  baseURL: "/api",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;

// -- Plants --

export function getPlants() {
  return api.get("/plants");
}

// -- Sessions --

export function getActiveSessions() {
  return api.get("/sessions/active");
}

// -- Telemetry (same contract as frontend/js/api.js fetchTelemetry) --

/**
 * @param {{
 *   hours?: number,
 *   plantId?: number | null,
 *   binSeconds?: number | "auto",
 *   sessionId?: number | null,
 * }} opts
 */
export function getTelemetryTimeseries(opts = {}) {
  const {
    hours = 24,
    plantId = null,
    binSeconds = "auto",
    sessionId = null,
  } = opts;

  const rangeHours = Math.min(Math.max(Number(hours) || 24, 1), 8760);
  let bin = 0;
  if (binSeconds === "auto") {
    if (rangeHours <= 6) bin = 0;
    else if (rangeHours <= 24) bin = 60;
    else if (rangeHours <= 72) bin = 300;
    else bin = 1800;
  } else {
    bin = Math.max(0, parseInt(binSeconds, 10) || 0);
  }

  const params = { hours: rangeHours };
  if (plantId != null && plantId !== "") {
    params.plant_ids = String(plantId);
  }
  if (bin > 0) params.bin_seconds = String(bin);
  if (sessionId != null) params.session_id = String(sessionId);

  return api.get("/telemetry/timeseries", { params });
}

// -- Anomaly Detection API (FR10) --

export function simulateAnomaly(scenario = "drift", durationMin = 30) {
  return api.post(`/anomalies/simulate?scenario=${encodeURIComponent(scenario)}&duration_min=${durationMin}`);
}

/** Persisted events (live / dummy ingest). */
export function listPersistedAnomalies(params = {}) {
  return api.get("/anomalies", { params });
}

/** @deprecated use listPersistedAnomalies */
export function getAnomalies(sessionId, filters = {}) {
  const params = { ...filters };
  if (sessionId != null) params.session_id = sessionId;
  return api.get("/anomalies", { params });
}

export function getAnomalySummary(sessionId) {
  return api.get(`/anomalies/summary/${sessionId}`);
}

export function clearAnomalies() {
  return api.delete("/anomalies/clear");
}

export function reprocessAnomalies(plantId, hours = 24) {
  return api.post(
    `/anomalies/reprocess?plant_id=${encodeURIComponent(plantId)}&hours=${encodeURIComponent(hours)}`
  );
}
