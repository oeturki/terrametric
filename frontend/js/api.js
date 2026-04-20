// ─────────────────────────────────────────────
//  api.js — All communication with the server
// ─────────────────────────────────────────────

// ── Low-level fetch helpers ──────────────────

async function apiFetch(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPut(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(API_BASE + path, { method: 'DELETE' });
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
  await Promise.allSettled([
    fetchLatest(),
    fetchTelemetry(),
    fetchAlerts(),
    fetchAnomalies(),
    fetchSamples(),
    fetchControls(),
    fetchGallery(),
  ]);
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
  } catch {
    const hint = document.getElementById('graphFilterHint');
    if (hint) { hint.style.display = 'none'; hint.textContent = ''; }
    const sessHint = document.getElementById('graphActiveSessionHint');
    if (sessHint) { sessHint.textContent = ''; sessHint.style.display = 'none'; }
    const meta = document.getElementById('graphRowMeta');
    if (meta) meta.textContent = 'offline';
    showChartsOffline();
  }
}

// ── Active alerts ────────────────────────────
// Returns: [{ id, severity, title, message, timestamp, resolved }, …]

async function fetchAlerts() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.alerts);
    const alerts = Array.isArray(data) ? data : data.alerts || [];
    alerts.forEach(a => {
      fireAlert(a.severity, a.title, a.message, a.severity === 'danger' ? 0 : 8000);
    });
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
    } else {
      // Empty server list -> wipe local stale state too so dropdowns clear.
      trays = [];
      if (typeof buildTrayList === 'function') buildTrayList();
      if (typeof buildGalleryTabs === 'function') buildGalleryTabs();
      if (typeof buildGalleryTimeline === 'function') buildGalleryTimeline();
    }
  } catch { /* use local trays */ }
  populateGraphSampleSelect(list);
}

// Re-fetch the sample list (and therefore re-render every consumer) whenever
// the canonical event bus tells us samples changed anywhere in the app.
window.addEventListener('samples:changed', function () {
  fetchSamples();
});

// ── Control variable settings ────────────────
// Returns: { group, temp_warn, temp_interval, hum_warn, … }

async function fetchControls() {
  try {
    const d = await apiFetch(CONFIG.ENDPOINTS.control);
    if (d.temp_warn)      document.getElementById('warn-temp').value     = d.temp_warn;
    if (d.temp_interval)  document.getElementById('int-temp').value      = d.temp_interval;
    if (d.hum_warn)       document.getElementById('warn-hum').value      = d.hum_warn;
    if (d.hum_interval)   document.getElementById('int-hum').value       = d.hum_interval;
    if (d.light_warn)     document.getElementById('warn-light').value    = d.light_warn;
    if (d.light_interval) document.getElementById('int-light').value     = d.light_interval;
    if (d.motion_interval)document.getElementById('int-motion').value    = d.motion_interval;
    if (d.height_warn)    document.getElementById('warn-height').value   = d.height_warn;
    if (d.height_interval)document.getElementById('int-height').value    = d.height_interval;
    if (d.cam_schedule)   document.getElementById('warn-cam').value      = d.cam_schedule;
    if (d.cam_interval)   document.getElementById('int-cam').value       = d.cam_interval;
  } catch { /* use defaults */ }
}

// ── Save control variables ───────────────────

async function saveControls() {
  const group = document.getElementById('groupSelect')?.value || 1;
  const payload = {
    group:           parseInt(group),
    temp_warn:       parseFloat(document.getElementById('warn-temp').value),
    temp_interval:   parseInt(document.getElementById('int-temp').value),
    hum_warn:        parseFloat(document.getElementById('warn-hum').value),
    hum_interval:    parseInt(document.getElementById('int-hum').value),
    light_warn:      parseFloat(document.getElementById('warn-light').value),
    light_interval:  parseInt(document.getElementById('int-light').value),
    motion_interval: parseInt(document.getElementById('int-motion').value),
    height_warn:     parseFloat(document.getElementById('warn-height').value),
    height_interval: parseInt(document.getElementById('int-height').value),
    cam_schedule:    document.getElementById('warn-cam').value,
    cam_interval:    parseInt(document.getElementById('int-cam').value),
  };
  try {
    await apiPost(CONFIG.ENDPOINTS.control, payload);
    fireAlert('ok', 'Settings Saved', 'Group ' + group + ' configuration updated.', 4000);
  } catch {
    fireAlert('warning', 'Save Failed', 'Could not reach server. Check your connection.', 5000);
  }
}

// ── Save a plant sample ──────────────────────

async function saveSample() {
  const sample = {
    name:  document.getElementById('d-name').value  || 'Unnamed Plant',
    loc:   document.getElementById('d-loc').value,
    germ:  document.getElementById('d-germ').value,
    notes: document.getElementById('d-notes').value,
    qr:    document.getElementById('d-qr').value,
  };
  trays[selectedTray] = sample;
  buildTrayList();
  buildGalleryTabs();
  buildGalleryTimeline();
  try {
    let serverRow;
    if (sample.id) {
      serverRow = await apiPut(CONFIG.ENDPOINTS.plants + '/' + sample.id, sample);
    } else {
      serverRow = await apiPost(CONFIG.ENDPOINTS.plants, sample);
    }
    if (serverRow && serverRow.id != null) {
      trays[selectedTray] = { ...trays[selectedTray], ...serverRow, id: serverRow.id };
      buildTrayList();
      if (typeof updateRecordingButtonState === 'function') updateRecordingButtonState();
      emitSamplesChanged(sample.id ? 'updated' : 'created', serverRow.id);
    }
    fireAlert('ok', 'Sample Saved', 'Sample ' + (selectedTray + 1) + ' saved.', 4000);
  } catch {
    fireAlert('info', 'Saved Locally', 'Sample saved in browser. Will sync when the system connects.', 4000);
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
