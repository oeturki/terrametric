/** FR10 - Anomaly Detection Test Page [Owner: Omer]
 *
 * Standalone page for testing the anomaly detection pipeline.
 * Pick a scenario, run the simulation, see the results.
 * Uses the same visual style as the Terrametric UI.
 */

import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceDot, Legend,
} from "recharts";
import { simulateAnomaly, clearAnomalies } from "../services/api";

const SCENARIOS = [
  { value: "stable", label: "Stable (no anomalies)", desc: "Normal sensor data -- should produce zero detections" },
  { value: "drift", label: "Drift", desc: "Temperature gradually increases over time (sensor calibration loss)" },
  { value: "noise", label: "Noise", desc: "Temperature becomes very jittery in the second half (sensor degradation)" },
  { value: "dropout", label: "Dropout", desc: "8-minute gap in the middle of the data (connection lost)" },
  { value: "all", label: "All Combined", desc: "Drift + noise + dropout in one session" },
];

const SEV_COLORS = { danger: "#a83232", warning: "#c4711a", info: "#4a7c8f" };
const SEV_BG = { danger: "#ffe0e0", warning: "#fff0c0", info: "#e0f0ff" };
const TYPE_ICONS = { drift: "📉", noise: "🔥", dropout: "📡" };

export default function AnomalyView() {
  const [scenario, setScenario] = useState("drift");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");

  async function runSimulation() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await simulateAnomaly(scenario, 30);
      setResult(res.data);
    } catch (err) {
      setError(err.message || "Failed to connect to backend. Is it running?");
    }
    setLoading(false);
  }

  async function handleClear() {
    try { await clearAnomalies(); } catch {}
    setResult(null);
  }

  const events = result?.events || [];
  const filtered = filter === "all" ? events : events.filter(e => e.type === filter);

  const chartData = (result?.readings || []).map(r => {
    const t = new Date(r.timestamp);
    return {
      time: t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      temperature: r.temperature,
      humidity: r.humidity,
      light: r.light,
    };
  });

  const anomalyMarkers = events.map(e => {
    const t = new Date(e.timestamp);
    const timeStr = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const point = chartData.find(d => d.time === timeStr);
    if (!point) return null;
    return { ...point, severity: e.severity, type: e.type };
  }).filter(Boolean);

  const selectedScenario = SCENARIOS.find(s => s.value === scenario);

  return (
    <div style={{ fontFamily: "'DM Mono', monospace", background: "#f5f2e8", minHeight: "100vh", padding: 0 }}>
      {/* Top bar */}
      <div style={{
        background: "#f5f2e8", borderBottom: "1px solid #e8e3d0", padding: "18px 36px",
        display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 50,
      }}>
        <div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 20 }}>Anomaly Detection Test</div>
          <div style={{ fontSize: 10, color: "#4a4730", letterSpacing: ".1em", marginTop: 2, textTransform: "uppercase" }}>
            FR10 -- Simulation & Verification
          </div>
        </div>
        <a href="/" style={{ fontSize: 11, color: "#4a4730", textDecoration: "none" }}>← Back to Dashboard</a>
      </div>

      <div style={{ padding: 36, maxWidth: 1200, margin: "0 auto" }}>
        {/* Scenario picker */}
        <div style={{
          background: "#2c2a1e", borderRadius: 14, padding: "24px 28px", color: "#f5f2e8", marginBottom: 28,
        }}>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14, marginBottom: 16, textTransform: "uppercase", letterSpacing: ".08em" }}>
            1. Choose a scenario
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
            {SCENARIOS.map(s => (
              <button key={s.value} onClick={() => setScenario(s.value)} style={{
                fontFamily: "'DM Mono', monospace", fontSize: 11, padding: "8px 16px", borderRadius: 20,
                cursor: "pointer", border: scenario === s.value ? "2px solid #b5c94a" : "2px solid rgba(255,255,255,0.15)",
                background: scenario === s.value ? "#7a8c1e" : "transparent",
                color: scenario === s.value ? "white" : "rgba(255,255,255,0.6)",
                transition: "all .15s",
              }}>
                {s.label}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 18 }}>{selectedScenario?.desc}</div>
          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={runSimulation} disabled={loading} style={{
              fontFamily: "'DM Mono', monospace", fontSize: 12, padding: "10px 24px", borderRadius: 6,
              cursor: loading ? "wait" : "pointer", border: "none",
              background: "#7a8c1e", color: "white", fontWeight: 600,
            }}>
              {loading ? "Running..." : "▶ Run Simulation"}
            </button>
            {result && (
              <button onClick={handleClear} style={{
                fontFamily: "'DM Mono', monospace", fontSize: 11, padding: "10px 16px", borderRadius: 6,
                cursor: "pointer", border: "1.5px solid rgba(255,255,255,0.2)", background: "transparent", color: "rgba(255,255,255,0.6)",
              }}>
                Clear
              </button>
            )}
          </div>
        </div>

        {error && (
          <div style={{
            background: "#fff5f5", border: "1px solid #e07070", borderRadius: 12, padding: "16px 20px",
            marginBottom: 24, fontSize: 12, color: "#8a1010",
          }}>
            <strong>Connection Error:</strong> {error}<br />
            <span style={{ fontSize: 10, opacity: 0.7 }}>Make sure the backend is running: cd backend && uvicorn main:app --reload --port 8000</span>
          </div>
        )}

        {result && (
          <>
            {/* Summary cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 24 }}>
              <SummaryCard icon="📊" count={result.total} label="Total Anomalies" color="#2c2a1e" />
              <SummaryCard icon="📉" count={result.drift} label="Drift Events" color="#4a7c8f" />
              <SummaryCard icon="🔥" count={result.spikes} label="Noise Spikes" color="#a83232" />
              <SummaryCard icon="📡" count={result.missing} label="Data Gaps" color="#c4711a" />
            </div>

            {/* Chart */}
            <div style={{
              background: "white", border: "1px solid #e8e3d0", borderRadius: 12, padding: 24, marginBottom: 24,
            }}>
              <div style={{
                fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 13, textTransform: "uppercase",
                letterSpacing: ".08em", marginBottom: 16,
              }}>
                Temperature Over Time ({result.readings_count} readings)
              </div>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e8e3d0" />
                  <XAxis dataKey="time" tick={{ fontSize: 9, fontFamily: "DM Mono" }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10, fontFamily: "DM Mono" }} />
                  <Tooltip contentStyle={{ fontFamily: "DM Mono", fontSize: 11 }} />
                  <Legend wrapperStyle={{ fontSize: 10, fontFamily: "DM Mono" }} />
                  <Line type="monotone" dataKey="temperature" stroke="#7a8c1e" strokeWidth={2} dot={false} name="Temperature (°C)" />
                  {anomalyMarkers.map((m, i) => (
                    <ReferenceDot key={i} x={m.time} y={m.temperature} r={5}
                      fill={SEV_COLORS[m.severity] || "#888"} stroke="white" strokeWidth={2} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 10, color: "#4a4730" }}>
                <span>● <span style={{ color: SEV_COLORS.danger }}>Red</span> = Critical</span>
                <span>● <span style={{ color: SEV_COLORS.warning }}>Orange</span> = Warning</span>
                <span>● <span style={{ color: SEV_COLORS.info }}>Blue</span> = Info</span>
              </div>
            </div>

            {/* Event log */}
            <div style={{ background: "white", border: "1px solid #e8e3d0", borderRadius: 12, overflow: "hidden" }}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid #e8e3d0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 13, textTransform: "uppercase", letterSpacing: ".08em" }}>
                  Anomaly Events ({filtered.length})
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  {["all", "drift", "noise", "dropout"].map(f => (
                    <button key={f} onClick={() => setFilter(f)} style={{
                      fontFamily: "'DM Mono', monospace", fontSize: 10, padding: "4px 12px", borderRadius: 20,
                      cursor: "pointer", border: filter === f ? "1.5px solid #7a8c1e" : "1.5px solid #e8e3d0",
                      background: filter === f ? "#7a8c1e" : "white",
                      color: filter === f ? "white" : "#4a4730",
                    }}>
                      {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Table header */}
              <div style={{
                display: "grid", gridTemplateColumns: "140px 100px 1fr 90px",
                background: "#e8e3d0", padding: "10px 20px", fontSize: 9, letterSpacing: ".15em",
                textTransform: "uppercase", color: "#4a4730",
              }}>
                <span>Timestamp</span><span>Sensor</span><span>Description</span><span>Severity</span>
              </div>

              {filtered.length === 0 ? (
                <div style={{ padding: 32, textAlign: "center", fontSize: 11, color: "#4a4730" }}>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>✅</div>
                  No anomalies detected for this filter
                </div>
              ) : (
                filtered.map((e, i) => (
                  <div key={i} style={{
                    display: "grid", gridTemplateColumns: "140px 100px 1fr 90px",
                    padding: "12px 20px", borderBottom: "1px solid #e8e3d0", fontSize: 11, alignItems: "center",
                  }}>
                    <span style={{ fontSize: 10 }}>{new Date(e.timestamp).toLocaleString()}</span>
                    <span>{TYPE_ICONS[e.type] || "⚠"} {e.sensor}</span>
                    <span style={{ fontSize: 10 }}>{e.description}</span>
                    <span>
                      <span style={{
                        fontSize: 8, padding: "3px 8px", borderRadius: 10, fontWeight: 700,
                        background: SEV_BG[e.severity] || "#eee",
                        color: SEV_COLORS[e.severity] || "#333",
                      }}>
                        {e.severity?.toUpperCase()}
                      </span>
                    </span>
                  </div>
                ))
              )}
            </div>
          </>
        )}

        {!result && !loading && !error && (
          <div style={{ textAlign: "center", padding: 60, color: "#4a4730" }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🧪</div>
            <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, marginBottom: 8 }}>
              Ready to test
            </div>
            <div style={{ fontSize: 11, lineHeight: 1.7, maxWidth: 400, margin: "0 auto" }}>
              Pick a scenario above and click Run Simulation.<br />
              The backend will generate synthetic sensor data, run it through<br />
              the drift, noise, and dropout detectors, and display the results here.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ icon, count, label, color }) {
  return (
    <div style={{
      background: "white", border: "1px solid #e8e3d0", borderRadius: 12, padding: 18,
      display: "flex", gap: 14, alignItems: "flex-start",
    }}>
      <div style={{ fontSize: 24 }}>{icon}</div>
      <div>
        <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 28, lineHeight: 1, color, marginBottom: 3 }}>
          {count}
        </div>
        <div style={{ fontSize: 9, letterSpacing: ".15em", textTransform: "uppercase", color: "#4a4730" }}>
          {label}
        </div>
      </div>
    </div>
  );
}
