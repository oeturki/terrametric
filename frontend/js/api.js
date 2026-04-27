// ─────────────────────────────────────────────
//  api.js — All communication with the server
// ─────────────────────────────────────────────

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

function populateGraphSampleSelect(plants) {
  const sel = document.getElementById('graphSample');
  if (!sel) return;
  const saved = sessionStorage.getItem(GRAPH_SAMPLE_STORAGE_KEY);
  sel.innerHTML = '';
  const optAll = document.createElement('option');
  optAll.value = '';
  optAll.textContent = 'All Samples (combined)';
  optAll.title =
    'All telemetry in the selected time window (every sample + any unscoped readings), one series.';
  sel.appendChild(optAll);
  for (const p of plants || []) {
    if (p == null || p.id == null) continue;
    const o = document.createElement('option');
    o.value = String(p.id);
    const parts = [p.name || 'Unnamed'];
    if (p.qr) parts.push(p.qr);
    o.textContent = parts.join(' · ');
    sel.appendChild(o);
  }
  if (saved !== null && saved !== undefined && [...sel.options].some(function (op) { return op.value === saved; })) {
    sel.value = saved;
  }
}

function onGraphSampleFilterChange() {
  const sel = document.getElementById('graphSample');
  if (sel) sessionStorage.setItem(GRAPH_SAMPLE_STORAGE_KEY, sel.value);
  fetchTelemetry();
}

/** Called from index.html when the time-range pill changes (was missing before). */
function onGraphRangeChange() {
  fetchTelemetry();
}

function onGraphSessionOnlyChange() {
  fetchTelemetry();
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
  }
}

// Detail-policy auto-binning: keep grain fine, only bin when raw would be huge.
//   1h  -> raw      (~1800 pts at 2s)
//   6h  -> raw      (~10800 pts; still OK on modern browsers, optional override)
//   24h -> 60s      (~1440 pts)
//   72h -> 300s     (~864 pts)
//   168h (7d) -> 1800s (~336 pts)
function _autoBinSeconds(rangeHours) {
  if (rangeHours <= 6)   return 0;
  if (rangeHours <= 24)  return 60;
  if (rangeHours <= 72)  return 300;
  return 1800;
}

async function fetchTelemetry() {
  const hourRange = parseInt(document.getElementById('graphRange')?.value || '24', 10);
  const sampleEl  = document.getElementById('graphSample');
  const plantId   = sampleEl && sampleEl.value ? String(sampleEl.value).trim() : '';
  const binSel    = document.getElementById('graphBin')?.value ?? 'auto';
  const binSeconds = binSel === 'auto' ? _autoBinSeconds(hourRange) : parseInt(binSel, 10);
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
        const scen = activeSess.scenario || 'stable';
        const mode = activeSess.dummy_stream ? 'Dummy stream' : 'Live device';
        const tick = activeSess.dummy_stream && activeSess.stream_interval_sec
          ? ' every ' + activeSess.stream_interval_sec + 's'
          : '';
        sessHint.textContent = mode + ' · session #' + activeSess.id + ' · scenario \u201c' + scen + '\u201d' + tick +
          '. Graphs plot all rows for this sample in the window unless \u201cThis recording only\u201d is checked.';
        sessHint.style.display = 'block';
      } else if (activeSess && !plantId) {
        sessHint.textContent = 'Recording active on plant #' + activeSess.plant_id +
          ' — select that sample above to match dummy scenario / session filter.';
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
    updateCharts(readings);
    if (typeof syncAnomalyChartsFromTelemetryPayload === 'function'
        && !window.anomSyntheticLabActive
        && document.getElementById('tab-anomalies')?.classList.contains('active')) {
      syncAnomalyChartsFromTelemetryPayload(d);
    }
  } catch {
    const hint = document.getElementById('graphFilterHint');
    if (hint) { hint.style.display = 'none'; hint.textContent = ''; }
    const sessHint = document.getElementById('graphActiveSessionHint');
    if (sessHint) { sessHint.textContent = ''; sessHint.style.display = 'none'; }
    const meta = document.getElementById('graphRowMeta');
    if (meta) meta.textContent = 'offline · demo series';
    const fallback = generateFallbackTelemetry(hourRange);
    updateCharts(fallback);
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
    const alerts = Array.isArray(data) ? data : data.alerts || [];
    // Toasts for newly seen ids only; then bind home + bell from server (single source of truth).
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

var TERRAMETRIC_VENT_STATE_KEY = 'terrametric_ventilation_on';

function _ventilationIsOn() {
  try {
    return localStorage.getItem(TERRAMETRIC_VENT_STATE_KEY) === '1';
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
    const blob = await res.blob();
    const u = URL.createObjectURL(blob);
    window.open(u, '_blank', 'noopener');
    fireAlert('ok', 'Camera', 'Picture captured — opened in a new tab.');
    setTimeout(function () {
      try { URL.revokeObjectURL(u); } catch (_) { /* ignore */ }
    }, 120000);
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
      localStorage.setItem(TERRAMETRIC_VENT_STATE_KEY, turningOn ? '1' : '0');
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
// Returns: [{ id, sample_qr, timestamp, height_cm, image_url }, …]

async function fetchGallery() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.camera);
    const photos = Array.isArray(data) ? data : data.images || [];
    galleryPhotos = {};
    photos.forEach(p => {
      const key = p.sample_qr || 'unknown';
      if (!galleryPhotos[key]) galleryPhotos[key] = [];
      galleryPhotos[key].push(p);
    });
    buildGalleryTimeline();
  } catch {
    buildGalleryTimeline();
  }
}
