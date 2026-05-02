/** FR10 — Live / dummy anomalies from persisted detector events. */

import { useState, useEffect, useMemo, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceDot, Legend,
} from "recharts";
import {
  listPersistedAnomalies,
  getTelemetryTimeseries,
  getPlants,
  getActiveSessions,
  reprocessAnomalies,
} from "../services/api";

const SEV_COLORS = { danger: "#a83232", warning: "#c4711a", info: "#4a7c8f" };
const SEV_BG = { danger: "#ffe0e0", warning: "#fff0c0", info: "#e0f0ff" };
const TYPE_ICONS = {
  spike: "⚡", drift: "📈", noise: "🔥", dropout: "📉", correlation: "🔗",
  level_shift: "🔀", ewma_breach: "📐", seasonal: "🌗",
};

const MATCH_MS = 120000;

function findNearestPointIndex(isoTs, rows) {
  const t = new Date(isoTs).getTime();
  if (!Number.isFinite(t)) return -1;
  let best = -1;
  let bestD = Infinity;
  for (let i = 0; i < rows.length; i++) {
    const d = Math.abs(new Date(rows[i].iso).getTime() - t);
    if (d < bestD) { bestD = d; best = i; }
  }
  return bestD <= MATCH_MS ? best : -1;
}

export default function AnomalyView() {
  const [plants, setPlants] = useState([]);
  const [plantId, setPlantId] = useState("");
  const [hours, setHours] = useState(24);
  const [sessionOnly, setSessionOnly] = useState(false);
  const [activeSessions, setActiveSessions] = useState([]);

  const [liveTelem, setLiveTelem] = useState(null);
  const [liveAnom, setLiveAnom] = useState(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveErr, setLiveErr] = useState(null);

  const [evtFilter, setEvtFilter] = useState("all");

  const [reprocBusy, setReprocBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [{ data: plist }, { data: act }] = await Promise.all([
          getPlants(),
          getActiveSessions(),
        ]);
        if (cancelled) return;
        const list = Array.isArray(plist) ? plist : plist.plants || [];
        setPlants(list);
        if (act?.sessions) setActiveSessions(act.sessions);
        else setActiveSessions([]);
      } catch {
        if (!cancelled) setPlants([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const activeForPlant = useMemo(() => {
    if (!plantId) return null;
    const pid = Number(plantId);
    return activeSessions.find((s) => Number(s.plant_id) === pid) || null;
  }, [plantId, activeSessions]);

  const canSessionOnly = !!(plantId && activeForPlant);

  const loadLive = useCallback(async () => {
    setLiveLoading(true);
    setLiveErr(null);
    try {
      const pid = plantId === "" ? null : Number(plantId);
      const sessId =
        canSessionOnly && sessionOnly && activeForPlant ? activeForPlant.id : null;

      const [tRes, aRes] = await Promise.all([
        getTelemetryTimeseries({
          hours,
          plantId: pid,
          binSeconds: "auto",
          sessionId: sessId,
        }),
        listPersistedAnomalies({
          hours,
          ...(pid != null && !Number.isNaN(pid) ? { plant_id: pid } : {}),
        }),
      ]);
      setLiveTelem(tRes.data);
      setLiveAnom(aRes.data);
    } catch (e) {
      setLiveErr(e.response?.data?.detail || e.message || "Failed to load");
      setLiveTelem(null);
      setLiveAnom(null);
    } finally {
      setLiveLoading(false);
    }
  }, [hours, plantId, sessionOnly, canSessionOnly, activeForPlant]);

  useEffect(() => {
    loadLive();
  }, [loadLive]);

  useEffect(() => {
    const id = setInterval(loadLive, 30000);
    return () => clearInterval(id);
  }, [loadLive]);

  const chartRows = useMemo(() => {
    const d = liveTelem;
    if (!d?.timestamps?.length) return [];
    return d.timestamps.map((iso, i) => ({
      iso,
      time: new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      temperature: d.temperature[i],
      humidity: d.humidity[i],
      light: d.light[i],
      height: d.plant_height[i],
    }));
  }, [liveTelem]);

  const liveEvents = liveAnom?.events || [];

  const tempMarkers = useMemo(() => {
    if (!chartRows.length || !liveEvents.length) return [];
    return liveEvents
      .filter((e) => e.sensor === "temperature" || e.sensor === "temperature+humidity")
      .map((e) => {
        const idx = findNearestPointIndex(e.timestamp, chartRows);
        if (idx < 0) return null;
        const row = chartRows[idx];
        return {
          ...row,
          severity: e.severity,
          type: e.type,
          description: e.description,
        };
      })
      .filter(Boolean);
  }, [chartRows, liveEvents]);

  const filteredLive = evtFilter === "all"
    ? liveEvents
    : liveEvents.filter((e) => e.type === evtFilter);

  async function handleReprocess() {
    if (!plantId) return;
    setReprocBusy(true);
    try {
      await reprocessAnomalies(Number(plantId), hours);
      await loadLive();
    } catch (e) {
      setLiveErr(e.response?.data?.detail || e.message || "Reprocess failed");
    }
    setReprocBusy(false);
  }

  const summary = liveAnom || {};

  return (
    <div style={{ fontFamily: "'DM Mono', monospace", background: "#f5f2e8", minHeight: "100vh", padding: 0 }}>
      <div style={{
        background: "#f5f2e8", borderBottom: "1px solid #e8e3d0", padding: "18px 36px",
        display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 50,
      }}>
        <div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 20 }}>Anomalies</div>
          <div style={{ fontSize: 10, color: "#4a4730", letterSpacing: ".1em", marginTop: 2, textTransform: "uppercase" }}>
            Live &amp; stored detector events
          </div>
        </div>
        <a href="/" style={{ fontSize: 11, color: "#4a4730", textDecoration: "none" }}>← Dashboard</a>
      </div>

      <div style={{ padding: 36, maxWidth: 1200, margin: "0 auto" }}>
        {/* Live */}
        <div style={{
          background: "#eef3e4", border: "1px solid #c8d4a8", borderRadius: 12, padding: "16px 20px", marginBottom: 24,
          fontSize: 11, color: "#2c3818",
        }}>
          <strong>Live &amp; stored</strong>
          {" "}— Charts use telemetry from the API; events come from persisted detector output (dummy stream and device ingest).
          Markers align readings within ±2 minutes for binned data.
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 20 }}>
          <label style={{ fontSize: 10, color: "#4a4730" }}>
            Sample{" "}
            <select
              value={plantId}
              onChange={(e) => { setPlantId(e.target.value); setSessionOnly(false); }}
              style={{ marginLeft: 6, padding: "6px 10px", borderRadius: 6, fontSize: 11 }}
            >
              <option value="">All my samples (combined)</option>
              {plants.map((p) => (
                <option key={p.id} value={String(p.id)}>{p.name || `Plant #${p.id}`} (#{p.id})</option>
              ))}
            </select>
          </label>
          <label style={{ fontSize: 10, color: "#4a4730" }}>
            Range{" "}
            <select
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              style={{ marginLeft: 6, padding: "6px 10px", borderRadius: 6, fontSize: 11 }}
            >
              <option value={1}>1 h</option>
              <option value={6}>6 h</option>
              <option value={24}>24 h</option>
              <option value={72}>72 h</option>
              <option value={168}>7 d</option>
            </select>
          </label>
          <label style={{ fontSize: 10, color: "#4a4730", opacity: canSessionOnly ? 1 : 0.45 }}>
            <input
              type="checkbox"
              checked={sessionOnly}
              disabled={!canSessionOnly}
              onChange={(e) => setSessionOnly(e.target.checked)}
            />
            {" "}This recording only
            {activeForPlant && canSessionOnly && (
              <span style={{ marginLeft: 4, color: "#7a8c1e" }}>· session #{activeForPlant.id}</span>
            )}
          </label>
          <button type="button" onClick={loadLive} disabled={liveLoading} style={{
            fontSize: 11, padding: "8px 16px", borderRadius: 6, border: "1px solid #c8c2b4",
            background: "white", cursor: liveLoading ? "wait" : "pointer",
          }}>
            {liveLoading ? "Loading…" : "↻ Refresh"}
          </button>
          <button
            type="button"
            onClick={handleReprocess}
            disabled={!plantId || reprocBusy}
            title="Replay telemetry in this window through detectors (requires a selected sample)"
            style={{
              fontSize: 11, padding: "8px 16px", borderRadius: 6, border: "1px dashed #7a8c1e",
              background: "#fafbf5", cursor: !plantId || reprocBusy ? "not-allowed" : "pointer",
            }}
          >
            {reprocBusy ? "Reprocessing…" : "Reprocess window"}
          </button>
        </div>

        {liveErr && (
          <div style={{
            background: "#fff5f5", border: "1px solid #e07070", borderRadius: 12, padding: "12px 16px",
            marginBottom: 20, fontSize: 12, color: "#8a1010",
          }}>
            {String(liveErr)}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 24 }}>
          <SummaryCard icon="📊" count={summary.total ?? 0} label="Total (window)" color="#2c2a1e" />
          <SummaryCard icon="📉" count={summary.drift ?? summary.by_type?.drift ?? 0} label="Drift" color="#4a7c8f" />
          <SummaryCard icon="⚡" count={summary.spike ?? summary.by_type?.spike ?? 0} label="Spikes" color="#a83232" />
          <SummaryCard icon="📡" count={summary.dropout ?? summary.by_type?.dropout ?? 0} label="Dropouts" color="#c4711a" />
        </div>

        <div style={{
          background: "white", border: "1px solid #e8e3d0", borderRadius: 12, padding: 24, marginBottom: 24,
        }}>
          <div style={{
            fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 13, textTransform: "uppercase",
            letterSpacing: ".08em", marginBottom: 8,
          }}>
            Temperature (live telemetry)
          </div>
          <div style={{ fontSize: 10, color: "#6a6648", marginBottom: 16 }}>
            {chartRows.length} points · auto binning · use sample + range controls above
          </div>
          {chartRows.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e8e3d0" />
                <XAxis dataKey="time" tick={{ fontSize: 9, fontFamily: "DM Mono" }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fontFamily: "DM Mono" }} />
                <Tooltip contentStyle={{ fontFamily: "DM Mono", fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 10, fontFamily: "DM Mono" }} />
                <Line type="monotone" dataKey="temperature" stroke="#7a8c1e" strokeWidth={2} dot={false} name="Temperature (°C)" />
                {tempMarkers.map((m, i) => (
                  <ReferenceDot
                    key={`${m.iso}-${i}`}
                    x={m.time}
                    y={m.temperature}
                    r={5}
                    fill={SEV_COLORS[m.severity] || "#888"}
                    stroke="white"
                    strokeWidth={2}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ padding: 40, textAlign: "center", color: "#826a5a", fontSize: 12 }}>
              No telemetry rows in this window. Record or backfill data, or widen the range.
            </div>
          )}
        </div>

        <div style={{ background: "white", border: "1px solid #e8e3d0", borderRadius: 12, overflow: "hidden", marginBottom: 32 }}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid #e8e3d0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 13, textTransform: "uppercase", letterSpacing: ".08em" }}>
              Stored events ({filteredLive.length})
            </span>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {["all", "spike", "drift", "noise", "dropout", "correlation"].map((f) => (
                <button key={f} type="button" onClick={() => setEvtFilter(f)} style={{
                  fontFamily: "'DM Mono', monospace", fontSize: 10, padding: "4px 12px", borderRadius: 20,
                  cursor: "pointer", border: evtFilter === f ? "1.5px solid #7a8c1e" : "1.5px solid #e8e3d0",
                  background: evtFilter === f ? "#7a8c1e" : "white",
                  color: evtFilter === f ? "white" : "#4a4730",
                }}>
                  {f === "all" ? "All" : f.replace("_", " ")}
                </button>
              ))}
            </div>
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: "140px 100px 1fr 90px",
            background: "#e8e3d0", padding: "10px 20px", fontSize: 9, letterSpacing: ".15em",
            textTransform: "uppercase", color: "#4a4730",
          }}>
            <span>Timestamp</span><span>Sensor</span><span>Description</span><span>Severity</span>
          </div>
          {!filteredLive.length ? (
            <div style={{ padding: 32, textAlign: "center", fontSize: 11, color: "#4a4730" }}>
              No events in this filter. Ingest telemetry to populate persisted anomalies.
            </div>
          ) : (
            filteredLive.map((e, i) => (
              <div
                key={e.id ?? `${e.timestamp}-${i}`}
                style={{
                  display: "grid", gridTemplateColumns: "140px 100px 1fr 90px",
                  padding: "12px 20px", borderBottom: "1px solid #e8e3d0", fontSize: 11, alignItems: "center",
                }}
              >
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
