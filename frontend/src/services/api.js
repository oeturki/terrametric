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

// -- Anomaly Detection API (FR10) --

export function simulateAnomaly(scenario = "drift", durationMin = 30) {
  return api.post(`/anomalies/simulate?scenario=${scenario}&duration_min=${durationMin}`);
}

export function getAnomalies(sessionId, filters = {}) {
  const params = { session_id: sessionId, ...filters };
  return api.get("/anomalies", { params });
}

export function getAnomalySummary(sessionId) {
  return api.get(`/anomalies/summary/${sessionId}`);
}

export function clearAnomalies() {
  return api.delete("/anomalies/clear");
}
