// ─────────────────────────────────────────────
//  api.js — All communication with the server
// ─────────────────────────────────────────────

/** Normalized map key for `galleryPhotos` (must stay aligned with lookups in samples.js). */
function normalizeGalleryQrKey(raw) {
  if (raw == null) return 'unknown';
  var s = String(raw).trim();
  if (s === '') return 'unknown';
  if (s.toLowerCase() === 'unknown') return 'unknown';
  return s.toUpperCase();
}

// ── Low-level fetch helpers ──────────────────

async function apiFetch(path) {
  const res = await authFetch(API_BASE + path);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await authFetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPostNoBody(path) {
  const res = await authFetch(API_BASE + path, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: '{}'
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** POST `/api/alerts/{id}/ack` — persists dismissal for one alert row. */
async function acknowledgeAlert(alertId) {
  const id = Number(alertId);
  if (!Number.isFinite(id) || id < 1) throw new Error('Invalid alert id');
  const path =
    typeof CONFIG.ENDPOINTS.alertsAck === 'function'
      ? CONFIG.ENDPOINTS.alertsAck(id)
      : '/api/alerts/' + id + '/ack';
  return apiPostNoBody(path);
}

/** POST `/api/alerts/ack-batch` with `{ ids: number[] }`. Falls back to per-id `/ack` if batch is unavailable. */
async function acknowledgeAlertsBatch(ids) {
  const clean = [
    ...new Set(
      (ids || [])
        .map(function (x) {
          return Number(x);
        })
        .filter(function (n) {
          return Number.isFinite(n) && n >= 1;
        })
    ),
  ];
  if (!clean.length) throw new Error('No alert ids');

  async function sequentialAckFallback() {
    const settled = await Promise.allSettled(clean.map(function (id) {
      return acknowledgeAlert(id);
    }));
    var ok = 0;
    settled.forEach(function (r) {
      if (r.status === 'fulfilled') ok += 1;
    });
    return { status: 'ok', acknowledged_count: ok, requested: clean.length };
  }

  var batchPath = '/api/alerts/ack-batch';
  try {
    if (CONFIG.ENDPOINTS && CONFIG.ENDPOINTS.alertsAckBatch) {
      batchPath = CONFIG.ENDPOINTS.alertsAckBatch;
    }
  } catch (_) { /* CONFIG missing in odd embed contexts */ }

  const res = await authFetch(API_BASE + batchPath, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ ids: clean }),
  });
  if (res.ok) return res.json();
  if (res.status === 404 || res.status === 405) return sequentialAckFallback();
  var detail = '';
  try {
    detail = await res.text();
    if (detail && detail.length > 220) detail = detail.slice(0, 220) + '…';
  } catch (_) { /* ignore */ }
  throw new Error('HTTP ' + res.status + (detail ? ' — ' + detail : ''));
}

async function apiPut(path, body) {
  const res = await authFetch(API_BASE + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiDelete(path) {
  const res = await authFetch(API_BASE + path, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

/**
 * Cross-page event bus for sample-list mutations (create / update / delete /
 * clear-telemetry / clear-all). Any view that displays sample-derived data
 * (Graphs picker, Gallery tabs, Anomalies filter, Home widgets) should listen
 * via `window.addEventListener('samples:changed', ...)` and re-render itself.
 *
 * Detail payload: { reason: 'created'|'updated'|'deleted'|'cleared'|'wiped',
 *                   plantId?: number }
 */
function emitSamplesChanged(reason, plantId) {
  try {
    window.dispatchEvent(new CustomEvent('samples:changed', {
      detail: { reason: reason, plantId: plantId == null ? null : Number(plantId) }
    }));
  } catch (_) { /* IE/old shims; non-fatal */ }
}

// ── Fetch all data at once ───────────────────

async function fetchAll() {
  // Samples must load before control profile: #groupSelect needs a plant_id, otherwise
  // fetchControls bails and the form stays on static HTML defaults.
  await Promise.allSettled([
    fetchLatest(),
    fetchTelemetry(),
    fetchAlerts(),
    fetchAnomalies(),
    fetchGallery(),
  ]);
  await fetchSamples();
}

// ── Latest sensor readings ───────────────────
// Returns: { temperature, humidity, light, height, motion, timestamp }

async function fetchLatest() {
  try {
    const d = await apiFetch(CONFIG.ENDPOINTS.latest);
    updateHomeStats(d);
    updateControlLiveVals(d);
  } catch {
    showOffline('home-temp');
  }
}

// ── Telemetry history ────────────────────────
// Returns: { readings: [{ temperature, humidity, light, height, timestamp }, …] }
// graphSample: empty = all data in window (combined); set = plant_id filter via API

const GRAPH_SAMPLE_STORAGE_KEY = 'terrametric-graph-sample';

/** When true, graph ↔ Anomalies duplicate controls are mirrored programmatically (avoids recursion). */
var _graphDupSync = false;

function _selectHasValue(selectEl, value) {
  if (!selectEl) return false;
  return [...selectEl.options].some(function (op) { return op.value === value; });
}

/** Copy canonical Graphs filter values onto the Anomalies-tab duplicates. */
function mirrorAnomalyDupFromGraph() {
  const gSel = document.getElementById('graphSample');
  const aSel = document.getElementById('anomSampleSelect');
  const gr = document.getElementById('graphRange');
  const ar = document.getElementById('anomGraphRange');
  const gb = document.getElementById('graphBin');
  const ab = document.getElementById('anomGraphBin');
  const gs = document.getElementById('graphSessionOnly');
  const as = document.getElementById('anomGraphSessionOnly');
  _graphDupSync = true;
  try {
    if (gSel && aSel && _selectHasValue(gSel, gSel.value) && _selectHasValue(aSel, gSel.value)) {
      aSel.value = gSel.value;
    }
    if (gr && ar && _selectHasValue(ar, gr.value)) ar.value = gr.value;
    if (gb && ab && _selectHasValue(ab, gb.value)) ab.value = gb.value;
    if (gs && as) {
      as.checked = gs.checked;
      as.disabled = gs.disabled;
    }
  } finally {
    _graphDupSync = false;
  }
}

/** Copy Anomalies-tab duplicate controls onto the canonical Graphs elements, then callers refresh data. */
function mirrorGraphFromAnomalyDup() {
  const gSel = document.getElementById('graphSample');
  const aSel = document.getElementById('anomSampleSelect');
  const gr = document.getElementById('graphRange');
  const ar = document.getElementById('anomGraphRange');
  const gb = document.getElementById('graphBin');
  const ab = document.getElementById('anomGraphBin');
  const gs = document.getElementById('graphSessionOnly');
  const as = document.getElementById('anomGraphSessionOnly');
  _graphDupSync = true;
  try {
    if (gSel && aSel && _selectHasValue(gSel, aSel.value)) {
      gSel.value = aSel.value;
      sessionStorage.setItem(GRAPH_SAMPLE_STORAGE_KEY, gSel.value);
    }
    if (gr && ar && _selectHasValue(gr, ar.value)) gr.value = ar.value;
    if (gb && ab && _selectHasValue(gb, ab.value)) gb.value = ab.value;
    if (gs && as && !gs.disabled) gs.checked = as.checked;
  } finally {
    _graphDupSync = false;
  }
}

function maybeRefreshAnomaliesAfterGraphFilterChange() {
  if (!document.getElementById('tab-anomalies')?.classList.contains('active')) return;
  /** When this tab is active, fetchTelemetry() awaits fetchAnomalies() — avoid racing with stale anomSimReadings here. */
  if (typeof refreshAnomalyPlantIdSessionHint === 'function') refreshAnomalyPlantIdSessionHint();
}

function populateGraphSampleSelect(plants) {
  const sel = document.getElementById('graphSample');
  const anomSel = document.getElementById('anomSampleSelect');
  const saved = sessionStorage.getItem(GRAPH_SAMPLE_STORAGE_KEY);

  function fillOne(selectEl) {
    if (!selectEl) return;
    selectEl.innerHTML = '';
    const optAll = document.createElement('option');
    optAll.value = '';
    optAll.textContent = 'All Samples (combined)';
    optAll.title =
      'All telemetry in the selected time window (every sample + any unscoped readings), one series.';
    selectEl.appendChild(optAll);
    for (const p of plants || []) {
      if (p == null || p.id == null) continue;
      const o = document.createElement('option');
      o.value = String(p.id);
      const parts = [p.name || 'Unnamed'];
      if (p.qr) parts.push(p.qr);
      o.textContent = parts.join(' · ');
      selectEl.appendChild(o);
    }
  }
  fillOne(sel);
  fillOne(anomSel);

  if (saved !== null && saved !== undefined && sel && [...sel.options].some(function (op) { return op.value === saved; })) {
    sel.value = saved;
    if (anomSel) anomSel.value = saved;
  }
  mirrorAnomalyDupFromGraph();
}

function onGraphSampleFilterChange() {
  const sel = document.getElementById('graphSample');
  if (sel) sessionStorage.setItem(GRAPH_SAMPLE_STORAGE_KEY, sel.value);
  if (!_graphDupSync) mirrorAnomalyDupFromGraph();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

/** Called from index.html when the time-range pill changes (was missing before). */
function onGraphRangeChange() {
  if (!_graphDupSync) mirrorAnomalyDupFromGraph();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

function onGraphBinChange() {
  if (!_graphDupSync) mirrorAnomalyDupFromGraph();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

function onGraphSessionOnlyChange() {
  if (!_graphDupSync) mirrorAnomalyDupFromGraph();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

function onAnomSampleFilterChange() {
  if (_graphDupSync) return;
  mirrorGraphFromAnomalyDup();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

function onAnomRangeChange() {
  if (_graphDupSync) return;
  mirrorGraphFromAnomalyDup();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

function onAnomBinChange() {
  if (_graphDupSync) return;
  mirrorGraphFromAnomalyDup();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

function onAnomSessionOnlyChange() {
  if (_graphDupSync) return;
  mirrorGraphFromAnomalyDup();
  fetchTelemetry();
  maybeRefreshAnomaliesAfterGraphFilterChange();
}

/**
 * Focus the View Data chart picker on a plant (e.g. after starting dummy recording
 * or backfill). No-op if the option is not in the list yet.
 */
function setGraphSampleForPlant(plantId) {
  if (plantId == null) return;
  const sel = document.getElementById('graphSample');
  if (!sel) return;
  const v = String(plantId);
  if ([...sel.options].some(function (op) { return op.value === v; })) {
    sel.value = v;
    sessionStorage.setItem(GRAPH_SAMPLE_STORAGE_KEY, v);
    mirrorAnomalyDupFromGraph();
  }
}

// Detail-policy auto-binning: keep grain fine, only bin when raw would be huge.
//   1h  -> raw      (~1800 pts at 2s)
//   6h  -> raw      (~10800 pts; still OK on modern browsers, optional override)
//   24h -> 60s      (~1440 pts)
//   72h -> 300s     (~864 pts)
//   168h (7d) -> 1800s (~336 pts)
function _autoBinSeconds(rangeHours) {
  const h = Number.isFinite(Number(rangeHours)) ? Number(rangeHours) : 24;
  if (h <= 6)   return 0;
  if (h <= 24)  return 60;
  if (h <= 72)  return 300;
  return 1800;
}

/** Canonical hours for telemetry + anomalies (avoid NaN which breaks FastAPI queries). */
function coerceGraphHourRange() {
  const raw = parseInt(document.getElementById('graphRange')?.value || '24', 10);
  if (!Number.isFinite(raw) || raw < 1) return 24;
  return Math.min(raw, 8760);
}

/** Shape used by Chart sync on the Anomalies tab (matches timeseries JSON). */
function readingsArrayToTelemetryPayload(readings) {
  return {
    timestamps: readings.map(function (r) { return r.timestamp; }),
    temperature: readings.map(function (r) { return r.temperature; }),
    humidity: readings.map(function (r) { return r.humidity; }),
    light: readings.map(function (r) { return r.light; }),
    plant_height: readings.map(function (r) {
      return r.height != null ? r.height : r.plant_height;
    }),
    bin_seconds: 0,
    row_count: readings.length,
  };
}

async function fetchTelemetry() {
  const hourRange = coerceGraphHourRange();
  const sampleEl  = document.getElementById('graphSample');
  const plantId   = sampleEl && sampleEl.value ? String(sampleEl.value).trim() : '';
  const binSel    = document.getElementById('graphBin')?.value ?? 'auto';
  const binParsed = parseInt(binSel, 10);
  const binSeconds = binSel === 'auto'
    ? _autoBinSeconds(hourRange)
    : (Number.isFinite(binParsed) ? binParsed : 0);
  const sessionOnlyEl = document.getElementById('graphSessionOnly');

  let activeSess = null;
  try {
    const act = await apiFetch(CONFIG.ENDPOINTS.sessionsActive);
    const sessions = act.sessions || [];
    activeSess = sessions[0] || null;
  } catch (_) {
    activeSess = null;
  }

  const canSessionOnly = !!(plantId && activeSess && Number(activeSess.plant_id) === Number(plantId));
  if (sessionOnlyEl) {
    sessionOnlyEl.disabled = !canSessionOnly;
    if (!canSessionOnly) sessionOnlyEl.checked = false;
  }
  const useSessionFilter = !!(canSessionOnly && sessionOnlyEl && sessionOnlyEl.checked);

  const params = new URLSearchParams({ hours: String(hourRange) });
  if (plantId)        params.set('plant_ids', plantId);
  if (binSeconds > 0) params.set('bin_seconds', String(binSeconds));
  if (useSessionFilter && activeSess) params.set('session_id', String(activeSess.id));

  const path = CONFIG.ENDPOINTS.telemetry + '?' + params.toString();
  try {
    const d = await apiFetch(path);
    const readings = [];
    for (let i = 0; i < d.timestamps.length; i++) {
      readings.push({
        timestamp: d.timestamps[i],
        temperature: d.temperature[i],
        humidity: d.humidity[i],
        light: d.light[i],
        height: d.plant_height[i]
      });
    }

    const sessHint = document.getElementById('graphActiveSessionHint');
    if (sessHint) {
      const pid = plantId ? Number(plantId) : null;
      if (activeSess && pid != null && Number(activeSess.plant_id) === pid) {
        let line;
        if (activeSess.dummy_stream) {
          const scen = activeSess.scenario || 'stable';
          let tick = '';
          if (activeSess.stream_interval_sec != null && activeSess.stream_interval_sec !== '') {
            const iv = Number(activeSess.stream_interval_sec);
            if (!isNaN(iv)) {
              tick = iv >= 1 ? (' every ' + iv + 's') : (' every ' + Math.round(iv * 1000) + 'ms');
            }
          }
          line = 'Dummy stream · session #' + activeSess.id + ' · scenario \u201c' + scen + '\u201d' + tick +
            ' (server-generated readings).';
        } else {
          line = 'Live recording · session #' + activeSess.id +
            ' · data is from device ingest only. The Manage Samples \u201cscenario\u201d is for dummy stream and is not applied now.';
        }
        line += ' Graphs show all rows for this sample in the window unless \u201cThis recording only\u201d is checked.';
        sessHint.textContent = line;
        sessHint.style.display = 'block';
      } else if (activeSess && !plantId) {
        sessHint.textContent = 'Recording active on plant #' + activeSess.plant_id +
          ' \u2014 pick that sample above to see session hints and filtering.';
        sessHint.style.display = 'block';
      } else {
        sessHint.textContent = '';
        sessHint.style.display = 'none';
      }
    }

    // Researcher meta-line: how many points and at what resolution.
    const meta = document.getElementById('graphRowMeta');
    if (meta) {
      const binTxt = binSeconds === 0 ? 'raw' : (binSeconds >= 3600 ? (binSeconds/3600)+'h' : (binSeconds >= 60 ? (binSeconds/60)+'min' : binSeconds+'s'));
      meta.textContent = 'n=' + readings.length + '  \u00b7  bin=' + binTxt +
        (plantId ? '  \u00b7  sample=' + plantId : '  \u00b7  all samples') +
        (useSessionFilter ? '  \u00b7  this session' : '');
    }

    const hint = document.getElementById('graphFilterHint');
    if (hint) {
      if (plantId && readings.length === 0) {
        hint.style.display = 'block';
        hint.textContent =
          'No telemetry for this sample in this window. Try \u201cAll Samples (combined)\u201d, widen the range, use Manage Samples to backfill or record, or turn off \u201cThis recording only\u201d if older/backfill rows should appear.';
      } else {
        hint.style.display = 'none';
        hint.textContent = '';
      }
    }
    mirrorAnomalyDupFromGraph();
    updateCharts(readings);
    if (typeof syncAnomalyChartsFromTelemetryPayload === 'function'
        && document.getElementById('tab-anomalies')?.classList.contains('active')) {
      syncAnomalyChartsFromTelemetryPayload(d);
      if (typeof fetchAnomalies === 'function') await fetchAnomalies();
    }
  } catch {
    const hint = document.getElementById('graphFilterHint');
    if (hint) {
      hint.style.display = 'block';
      hint.textContent =
        'Telemetry API unreachable or error — graphs show browser-only demo curves, not Arduino data. Fix login, API_BASE in config.js, and that the backend is running; then reload.';
    }
    const sessHint = document.getElementById('graphActiveSessionHint');
    if (sessHint) { sessHint.textContent = ''; sessHint.style.display = 'none'; }
    const meta = document.getElementById('graphRowMeta');
    if (meta) meta.textContent = 'offline · demo series (not from server)';
    mirrorAnomalyDupFromGraph();
    const fallback = generateFallbackTelemetry(hourRange);
    updateCharts(fallback);
    var dFb = readingsArrayToTelemetryPayload(fallback);
    if (typeof syncAnomalyChartsFromTelemetryPayload === 'function'
        && document.getElementById('tab-anomalies')?.classList.contains('active')) {
      syncAnomalyChartsFromTelemetryPayload(dFb);
      if (typeof fetchAnomalies === 'function') await fetchAnomalies();
    }
  }
}

function generateFallbackTelemetry(hours = 24) {
  const readings = [];
  const baseTime = new Date();
  baseTime.setHours(baseTime.getHours() - hours);

  for (let i = 0; i < hours; i++) {
    const timestamp = new Date(baseTime);
    timestamp.setHours(timestamp.getHours() + i);

    readings.push({
      timestamp: timestamp.toISOString(),
      temperature: parseFloat((18 + Math.random() * 14).toFixed(2)),
      humidity: parseFloat((40 + Math.random() * 45).toFixed(2)),
      light: parseFloat((50 + Math.random() * 1450).toFixed(2)),
      height: parseFloat((10 + Math.random() * 30).toFixed(2))
    });
  }
  return readings;
}

// ── Active alerts ────────────────────────────
// Returns: [{ id, severity, title, message, timestamp, resolved }, …]

const _seenAlertIds = new Set();
const _SEEN_MAX = 400;

async function fetchAlerts() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.alerts);
    const alertsRaw = Array.isArray(data) ? data : data.alerts || [];
    if (typeof registerLastServerAlertsSnapshot === 'function') {
      registerLastServerAlertsSnapshot(alertsRaw);
    }
    const alerts = alertsRaw;
    // Toasts only for alerts we still show — and only once per numeric id until tab reload clears _seenAlertIds.
    alerts.forEach(a => {
      if (a.id != null) {
        if (_seenAlertIds.has(a.id)) return;
        if (_seenAlertIds.size >= _SEEN_MAX) {
          _seenAlertIds.clear();
        }
        _seenAlertIds.add(a.id);
      }
      fireAlert(a.severity, a.title, a.message, a.severity === 'danger' ? 0 : 8000);
    });
    if (typeof renderHomeAlertFeedFromServer === 'function') {
      renderHomeAlertFeedFromServer(alerts);
    }
    if (typeof syncServerAlertsToDropdown === 'function') {
      syncServerAlertsToDropdown(alerts);
    }
  } catch { /* alerts endpoint not ready yet */ }
}

// ── Plant samples ────────────────────────────
// Returns: [{ id, name, loc, germ, notes, qr }, …]

async function fetchSamples() {
  let list = [];
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.plants);
    list = Array.isArray(data) ? data : data.plants || [];
  if (list.length) {
    trays = list;
    buildTrayList();
    selectTray(0);
    buildGalleryTabs();
    populateGraphSampleSelect(list);
    if (typeof buildGalleryTimeline === 'function') buildGalleryTimeline();
    if (typeof buildControlPlantSelectFromList === 'function') {
      buildControlPlantSelectFromList(list);
    }
  }
  // ❗ do nothing if empty — prevents wiping UI due to auth/race issues
  } catch (e) {
    console.warn('fetchSamples failed — keeping existing trays', e);
    return; // ❗ stop here, do NOT continue
  }
  if (typeof fetchControls === 'function') {
    await fetchControls();
  }
}

// Re-fetch the sample list (and therefore re-render every consumer) whenever
// the canonical event bus tells us samples changed anywhere in the app.
window.addEventListener('samples:changed', function () {
  fetchSamples();
});

// Control variables: fetchControls / saveControls / resetControls / cancelChanges
// are defined in config.js (nested JSON for /api/control). Do not redefine here.

// ── Save a plant sample ──────────────────────

async function saveSample() {
  const prev = trays[selectedTray] || {};
  const sample = {
    name:  document.getElementById('d-name').value  || 'Unnamed Plant',
    loc:   document.getElementById('d-loc').value,
    germ:  document.getElementById('d-germ').value,
    notes: document.getElementById('d-notes').value,
    qr:    document.getElementById('d-qr').value,
  };
  // Keep any server `id` (and other fields) if this save fails — old code dropped `id` and broke recording.
  const merged = { ...prev, ...sample };
  trays[selectedTray] = merged;
  buildTrayList();
  buildGalleryTabs();
  buildGalleryTimeline();
  if (typeof updateRecordingButtonState === 'function') updateRecordingButtonState();

  const existingId = merged.id;
  const path = existingId
    ? CONFIG.ENDPOINTS.plants + '/' + existingId
    : CONFIG.ENDPOINTS.plants;
  const method = existingId ? 'PUT' : 'POST';

  try {
    const res = await authFetch(API_BASE + path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sample),
    });
    if (res.status === 401) {
      return;
    }
    if (!res.ok) {
      let detail = 'HTTP ' + res.status;
      const text = await res.text();
      try {
        const j = JSON.parse(text);
        if (j.detail != null) {
          detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
        }
      } catch (_) {
        if (text) detail = text.length > 300 ? text.slice(0, 300) + '…' : text;
      }
      // 409: QR already in this account (common when default TM-S00n collides with an existing id).
      if (res.status === 409 && typeof nextFreeTmQr === 'function' && typeof trays !== 'undefined') {
        var serverQrs = [];
        try {
          const pr = await authFetch(API_BASE + CONFIG.ENDPOINTS.plants);
          if (pr.ok) {
            const pdata = await pr.json();
            const plist = Array.isArray(pdata) ? pdata : pdata.plants || [];
            serverQrs = plist.map(function (p) { return p && p.qr; }).filter(Boolean);
          }
        } catch (_) { /* ignore */ }
        var nq = nextFreeTmQr(serverQrs);
        var cur = trays[selectedTray];
        if (cur) {
          cur.qr = nq;
        }
        var dqr = document.getElementById('d-qr');
        if (dqr) dqr.value = nq;
        if (typeof buildTrayList === 'function') buildTrayList();
        if (typeof selectTray === 'function' && typeof selectedTray === 'number') {
          selectTray(selectedTray);
        }
        if (typeof fireAlert === 'function') {
          fireAlert(
            'info',
            'QR already in use',
            'The server already has a sample with that code. Suggested: ' + nq + ' — save again to create or update this row.',
            8000
          );
        }
        return;
      }
      throw new Error(detail);
    }
    const serverRow = await res.json();
    if (serverRow && serverRow.id != null) {
      trays[selectedTray] = { ...trays[selectedTray], ...serverRow, id: serverRow.id };
      buildTrayList();
      if (typeof updateRecordingButtonState === 'function') updateRecordingButtonState();
      emitSamplesChanged(existingId ? 'updated' : 'created', serverRow.id);
    }
    fireAlert('ok', 'Sample Saved', 'Sample ' + (selectedTray + 1) + ' saved to the server.', 4000);
  } catch (e) {
    const msg = e && e.message ? String(e.message) : 'Request failed';
    if (e && e.name === 'TypeError' && (msg.indexOf('fetch') >= 0 || msg.indexOf('Load failed') >= 0 || msg.indexOf('NetworkError') >= 0)) {
      fireAlert('danger', 'Save failed', 'Cannot reach the API at ' + API_BASE + '. Start the backend and ensure `PORT` in js/config.js matches the server (default 8000).', 9000);
      return;
    }
    fireAlert('warning', 'Could not save on the server', msg + ' — Sign in at login.html if needed; the form data is still in this page.', 9000);
  }
}

// ── Home: Pi camera + ventilation (laptop API proxies to `pi/hardware_agent.py`) ──

// Toggle state is session-only (not localStorage): a stale "on" flag used to make the *next* click
// send { on: false } (servo detach) while the user expects "Activate" after fixing the Pi / BT link.
var TERRAMETRIC_VENT_STATE_KEY = 'terrametric_ventilation_on';

function _ventilationIsOn() {
  try {
    return sessionStorage.getItem(TERRAMETRIC_VENT_STATE_KEY) === '1';
  } catch (_) {
    return false;
  }
}

/** Sync Home tile label + aria with stored toggle (call on load and after each successful click). */
function syncVentilationButtonLabel() {
  var on = _ventilationIsOn();
  var label = document.getElementById('ventLabel');
  var btn = document.getElementById('ventilationNavBtn');
  if (label) {
    label.textContent = on ? 'Deactivate ventilation' : 'Activate ventilation';
  }
  if (btn) {
    btn.setAttribute('data-vent-active', on ? '1' : '0');
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncVentilationButtonLabel);
  } else {
    syncVentilationButtonLabel();
  }
}

async function homeHardwareCapture(ev) {
  if (ev && ev.stopPropagation) ev.stopPropagation();
  try {
    const res = await authFetch(API_BASE + CONFIG.ENDPOINTS.hardwareCapture, { method: 'POST' });
    if (!res.ok) {
      let msg = await res.text();
      try {
        const j = JSON.parse(msg);
        if (j.detail !== undefined) {
          msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
        }
      } catch (_) { /* keep text */ }
      throw new Error(msg || ('HTTP ' + res.status));
    }
    try {
      await res.blob();
    } catch (_) { /* ignore body */ }
    const persisted = typeof res.headers.get === 'function' && res.headers.get('X-Capture-Persisted') === '1';
    try {
      if (persisted) {
        await fetchGallery();
      }
    } catch (_) { /* noop */ }
    try {
      if (persisted && typeof fetchAlerts === 'function') await fetchAlerts();
    } catch (_) { /* noop */ }
    if (!persisted) {
      fireAlert(
        'warning',
        'Camera',
        'Picture taken but not saved — start recording for your sample first, then try again.',
        8000,
      );
    }
  } catch (e) {
    const m = e && e.message ? String(e.message) : String(e);
    fireAlert('danger', 'Camera', m, 8000);
  }
}

async function homeHardwareVentilation(ev) {
  if (ev && ev.stopPropagation) ev.stopPropagation();
  var turningOn = !_ventilationIsOn();
  try {
    const res = await authFetch(API_BASE + CONFIG.ENDPOINTS.hardwareVentilation, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        turningOn ? { on: true, spin: true } : { on: false, spin: false }
      )
    });
    const text = await res.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { detail: text }; }
    if (!res.ok) {
      const d = data.detail;
      const msg = typeof d === 'string' ? d : (text || ('HTTP ' + res.status));
      throw new Error(msg);
    }
    try {
      sessionStorage.setItem(TERRAMETRIC_VENT_STATE_KEY, turningOn ? '1' : '0');
    } catch (_) { /* ignore */ }
    syncVentilationButtonLabel();
    var okMsg = (data && data.detail) ? String(data.detail) : (turningOn ? 'Ventilation on' : 'Ventilation off');
    fireAlert('ok', 'Ventilation', okMsg, 5000);
  } catch (e) {
    const m = e && e.message ? String(e.message) : String(e);
    fireAlert('danger', 'Ventilation', m, 8000);
  }
}

// ── Camera gallery images ────────────────────
// Metadata only (no thumbnail prefetch). Optional optPlantId → GET ?plant_id= merge.

async function fetchGallery(optPlantId) {
  try {
    const qs =
      typeof optPlantId === 'number' && !isNaN(optPlantId) && optPlantId >= 1
        ? '?plant_id=' + encodeURIComponent(String(Math.floor(optPlantId)))
        : '';
    const data = await apiFetch(CONFIG.ENDPOINTS.camera + qs);
    const photos = Array.isArray(data) ? data : data.images || [];

    const groupByQr = function (list) {
      const o = {};
      list.forEach(function (p) {
        const key = normalizeGalleryQrKey(p.sample_qr);
        if (!o[key]) o[key] = [];
        o[key].push(p);
      });
      return o;
    };

    if (qs) {
      const patch = groupByQr(photos);
      Object.keys(patch).forEach(function (key) {
        galleryPhotos[key] = patch[key];
      });
    } else {
      galleryPhotos = groupByQr(photos);
    }

    if (typeof buildGalleryTimeline === 'function') buildGalleryTimeline();
    if (typeof updateGalleryActionsBar === 'function') updateGalleryActionsBar();
  } catch (_) {
    if (typeof buildGalleryTimeline === 'function') buildGalleryTimeline();
    if (typeof updateGalleryActionsBar === 'function') updateGalleryActionsBar();
  }
}
