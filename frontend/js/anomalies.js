// ─────────────────────────────────────────────
//  anomalies.js — Anomaly detection (View Data → Anomalies tab).
// ─────────────────────────────────────────────

let anomalyLog = [];

/** Min visible x-span when zooming (matches Graphs tab). */
const ANOM_ZOOM_X_MIN_MS = 60 * 1000;

const ANOM_PAGE_SIZE = 45;
let anomLogVisible = ANOM_PAGE_SIZE;
let anomAckKeys = new Set();
let anomFocusTs = null;

let anomSimReadings = [];
let anomSimActiveSensors = new Set(['temperature']);
/** From last telemetry sync (ms tolerance for snapping events to binned points). */
let anomTelemetryBinSeconds = 0;

/** Keeps anomaly charts stable across harmless fetchAnomalies() polls while this matches. */
let _lastAnomalyVizSig = null;

function invalidateAnomalyVizCache() {
  _lastAnomalyVizSig = null;
}

function _rollupFingerprintStr(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return h >>> 0;
}

function anomTelemetryFingerprint() {
  const n = anomSimReadings.length;
  if (!n) return 'e0';
  let roll = 0;
  const stride = Math.max(1, Math.floor(n / 500));
  for (let i = 0; i < n; i += stride) {
    const r = anomSimReadings[i];
    const blob =
      String(r.timestamp) +
      '\x1e' +
      String(r.temperature ?? '') +
      '\x1e' +
      String(r.humidity ?? '') +
      '\x1e' +
      String(r.light ?? '') +
      '\x1e' +
      String(r.height ?? '');
    roll ^= _rollupFingerprintStr(blob);
    roll >>>= 0;
  }
  return (
    'n' +
      n +
      '|' +
      anomSimReadings[0].timestamp +
      '|' +
      anomSimReadings[n - 1].timestamp +
      '|' +
      roll.toString(36) +
      '|bin' +
      String(anomTelemetryBinSeconds ?? 0)
  );
}

function anomEventsFingerprint() {
  const n = anomalyLog.length;
  if (!n) return 'e0';
  let roll = 0;
  const stride = Math.max(1, Math.floor(n / 600));
  for (let i = 0; i < n; i += stride) {
    const e = anomalyLog[i];
    const blob =
      String(e.timestamp) +
      '\x1e' +
      String(e.type ?? '') +
      '\x1e' +
      String(e.sensor ?? '') +
      '\x1e' +
      String(e.severity ?? '');
    roll ^= _rollupFingerprintStr(blob);
    roll >>>= 0;
  }
  return (
    'ev' +
      n +
      '|' +
      anomalyLog[0].timestamp +
      '|' +
      anomalyLog[n - 1].timestamp +
      '|' +
      roll.toString(36)
  );
}

function buildAnomalyVizSig() {
  const markers = document.getElementById('anomShowMarkers')?.checked !== false ? '1' : '0';
  const sensors = [...anomSimActiveSensors].sort().join(',');
  return markers + '|' + sensors + '|' + anomTelemetryFingerprint() + '|' + anomEventsFingerprint();
}

/**
 * Full redraw Anomalies tab charts unless data + UI prefs match last render (polling safe).
 * @param {boolean} [force] — redraw even when signature unchanged (UI toggles).
 */
function refreshAnomalyTabCharts(force) {
  if (!document.getElementById('tab-anomalies')?.classList.contains('active')) return;
  const sig = buildAnomalyVizSig();
  if (!force && _lastAnomalyVizSig === sig) return;

  renderAnomCharts();
  renderAnomalyScoreTimeline();

  if (anomSimReadings.length) _lastAnomalyVizSig = sig;
  else invalidateAnomalyVizCache();
}

function anomAlignmentMaxDeltaMs() {
  const b = Number(anomTelemetryBinSeconds);
  if (Number.isFinite(b) && b > 0) return b * 1000 + 120000;
  return 120000;
}

/** Max ms between an event timestamp and a plotted telemetry point we'll treat as same bucket. */
function anomSnapToleranceMs() {
  const alignment = anomAlignmentMaxDeltaMs();
  if (anomSimReadings.length < 2) return alignment;
  const t0 = anomTimestampToMs(anomSimReadings[0].timestamp);
  const t1 = anomTimestampToMs(anomSimReadings[anomSimReadings.length - 1].timestamp);
  if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) return alignment;
  const spanMs = t1 - t0;
  const stepEst = spanMs / Math.max(anomSimReadings.length - 1, 1);
  const widened = Math.max(alignment, Math.min(stepEst * 96, alignment * 6));
  return Math.min(Math.max(widened, alignment), alignment + spanMs / 24);
}

function anomTimestampToMs(ts) {
  const n = new Date(ts).getTime();
  return Number.isFinite(n) ? n : NaN;
}

function anomalyEventMatchesSensor(evt, sensor) {
  const sRaw = evt && evt.sensor != null ? String(evt.sensor).trim() : '';
  if (!sRaw) return false;
  const s = sRaw.toLowerCase();
  const ch = String(sensor || '').trim().toLowerCase();
  if (!ch) return false;
  if (s === 'all') return true;
  if (ch === 'temperature' && s === 'temperature+humidity') return true;
  if ((ch === 'height' || ch === 'plant_height') && (s === 'height' || s === 'plant_height')) return true;
  return s === ch;
}

function anomEventsNearReadingTs(readingTs) {
  const t0 = new Date(readingTs).getTime();
  if (!Number.isFinite(t0)) return [];
  const maxW = anomSnapToleranceMs();
  return anomalyLog.filter(e => {
    const ta = new Date(e.timestamp).getTime();
    return Number.isFinite(ta) && Math.abs(ta - t0) <= maxW;
  });
}

function anomMedianStepMs() {
  if (anomSimReadings.length < 2) return 60000;
  const deltas = [];
  const lim = Math.min(anomSimReadings.length - 1, 500);
  for (let i = 0; i < lim; i++) {
    const a = anomTimestampToMs(anomSimReadings[i].timestamp);
    const b = anomTimestampToMs(anomSimReadings[i + 1].timestamp);
    if (Number.isFinite(a) && Number.isFinite(b)) {
      const d = Math.abs(b - a);
      if (d > 0 && d < 86400000) deltas.push(d);
    }
  }
  if (!deltas.length) return 60000;
  deltas.sort(function (x, y) { return x - y; });
  return deltas[deltas.length >> 1];
}

/** Narrow follow-up bracket so many events near the tail do not all snap to one plotted bucket. */
function anomSecondaryReadingMatchMs() {
  const snap = anomSnapToleranceMs();
  const step = anomMedianStepMs();
  return Math.min(Math.max(snap * 2.5, step * 56), snap * 5, 240000);
}

/** Tooltip should list only anomalies genuinely near the hovered x (avoid multi-minute blobs). */
function anomTooltipMatchWindowMs() {
  const snap = anomSnapToleranceMs();
  const step = anomMedianStepMs();
  return Math.min(Math.max(step * 20, 3000), snap, 60000);
}

function anomResolveReadingIndexForEvent(ts) {
  if (!anomSimReadings.length || ts == null) return -1;
  const target =
    typeof ts === 'number' && Number.isFinite(ts)
      ? ts
      : new Date(ts).getTime();
  if (!Number.isFinite(target)) return -1;
  let best = -1;
  let bestDiff = Infinity;
  for (let i = 0; i < anomSimReadings.length; i++) {
    const t = new Date(anomSimReadings[i].timestamp).getTime();
    if (!Number.isFinite(t)) continue;
    const d = Math.abs(t - target);
    if (d < bestDiff) {
      bestDiff = d;
      best = i;
    }
  }
  if (best < 0) return -1;
  if (bestDiff <= anomSnapToleranceMs()) return best;
  if (bestDiff <= anomSecondaryReadingMatchMs()) return best;
  return -1;
}

/**
 * XY for anomaly scatter markers aligned to the plotted telemetry curve.
 *
 * Previously the code placed X at event time but Y from the snapped reading row alone.
 * With coarse buckets or permissive snapping, nearest-row Y could stick to an early plateau
 * while X moved across the window — triangles formed a misleading horizontal ribbon above
 * a later dive. Linear interpolation between adjacent plotted points fixes that.
 */
function anomInterpolateReadingPointAt(sensor, tMs) {
  const rs = anomSimReadings;
  if (!rs.length || !Number.isFinite(tMs)) return null;

  const yOf = idx => {
    const v = rs[idx][sensor];
    if (v == null || !Number.isFinite(Number(v))) return null;
    return Number(v);
  };

  const tOf = idx => anomTimestampToMs(rs[idx].timestamp);

  const tFirst = tOf(0);
  const tLast = tOf(rs.length - 1);
  if (!Number.isFinite(tFirst) || !Number.isFinite(tLast)) return null;

  if (tMs <= tFirst) {
    const y = yOf(0);
    return y != null ? { x: tFirst, y } : null;
  }
  if (tMs >= tLast) {
    const y = yOf(rs.length - 1);
    return y != null ? { x: tLast, y } : null;
  }

  for (let i = 0; i < rs.length - 1; i++) {
    const t0 = tOf(i);
    const t1 = tOf(i + 1);
    if (!Number.isFinite(t0) || !Number.isFinite(t1)) continue;
    if (tMs < t0 || tMs > t1) continue;

    const y0 = yOf(i);
    const y1 = yOf(i + 1);
    if (y0 == null || y1 == null) return null;

    const u = t1 === t0 ? 0 : (tMs - t0) / (t1 - t0);
    return { x: tMs, y: y0 + u * (y1 - y0) };
  }

  /** Rare non-monotonic timestamps: fall back to nearest-row point on the curve */
  let ix = anomResolveReadingIndexForEvent(tMs);
  if (ix < 0) return null;
  const tx = tOf(ix);
  const yy = yOf(ix);
  if (!Number.isFinite(tx) || yy == null) return null;
  return { x: tx, y: yy };
}
function updateAnomDataSourceBanner() {
  const el = document.getElementById('anomDataSourceBanner');
  if (!el) return;
  const rangeEl = document.getElementById('graphRange');
  const rangeLabel =
    document.getElementById('tab-anomalies')?.classList.contains('active')
      ? document.getElementById('anomGraphRange')?.selectedOptions[0]?.textContent
      : rangeEl?.selectedOptions[0]?.textContent;
  const rangeDisp = rangeLabel || rangeEl?.selectedOptions[0]?.textContent || '';
  const pid = document.getElementById('graphSample')?.value;
  el.textContent = pid
    ? ('Live telemetry · ' + rangeDisp + ' · sample #' + pid)
    : ('Live telemetry · ' + rangeDisp + ' · all samples combined');
  el.classList.remove('anom-banner--lab');
}

async function refreshAnomalyPlantIdSessionHint() {
  const line = document.getElementById('anomActiveSessionLine');
  if (!line) return;
  if (!document.getElementById('tab-anomalies')?.classList.contains('active')) return;
  const plantId = (document.getElementById('graphSample')?.value || '').trim();
  try {
    const act = await apiFetch(CONFIG.ENDPOINTS.sessionsActive);
    const sessions = act.sessions || [];
    const active = sessions[0] || null;
    if (!plantId) {
      line.textContent = active
        ? ' Tip: Active recording on sample #' + active.plant_id + ' — select that sample above so charts and the anomaly list match that stream.'
        : '';
      return;
    }
    const pid = Number(plantId);
    if (active && Number(active.plant_id) === pid) {
      line.textContent =
        ' Session #' + active.id + ' active for this sample — telemetry ingested during recording should carry plant_id for live persistence.';
    } else {
      line.textContent =
        ' No active recording for this sample — if live rows lack plant_id, start recording in Manage Samples or set the bridge plant id, then use Reprocess window.';
    }
  } catch {
    line.textContent = '';
  }
}

/**
 * Called from fetchTelemetry when the Anomalies tab is visible — keeps charts aligned with View Data.
 */
function syncAnomalyChartsFromTelemetryPayload(d) {
  if (!d || !Array.isArray(d.timestamps) || !d.timestamps.length) {
    anomTelemetryBinSeconds = 0;
    anomSimReadings = [];
    updateAnomDataSourceBanner();
    buildAnomSensorPills();
    const wrap = document.getElementById('anomChartWrap');
    const score = document.getElementById('anomScoreWrap');
    if (wrap) {
      wrap.innerHTML = '<div class="anom-placeholder"><span class="anom-placeholder__glyph" aria-hidden="true">◇</span><p class="anom-placeholder__text">No telemetry in this window for the current filters. Pick a sample or widen the range using the filters above.</p></div>';
    }
    if (score) {
      score.innerHTML = '<div class="anom-placeholder anom-placeholder--compact"><p class="anom-placeholder__text">No data in range.</p></div>';
    }
    if (charts.anomSim) { for (const c of Object.values(charts.anomSim)) { if (c && c.destroy) c.destroy(); } charts.anomSim = null; }
    if (charts.anomScore && charts.anomScore.destroy) { charts.anomScore.destroy(); charts.anomScore = null; }
    invalidateAnomalyVizCache();
    return;
  }
  anomTelemetryBinSeconds =
    d.bin_seconds != null && !Number.isNaN(Number(d.bin_seconds)) ? Number(d.bin_seconds) : 0;
  anomSimReadings = [];
  for (let i = 0; i < d.timestamps.length; i++) {
    anomSimReadings.push({
      timestamp: d.timestamps[i],
      temperature: d.temperature[i],
      humidity: d.humidity[i],
      light: d.light[i],
      height: d.plant_height[i]
    });
  }
  updateAnomDataSourceBanner();
  buildAnomSensorPills();
}

/** Plant id for View Data → Anomalies: sync graph picker from anomalies dropdown, then read either. */
function getViewDataPlantId() {
  if (
    typeof mirrorGraphFromAnomalyDup === 'function' &&
    document.getElementById('tab-anomalies')?.classList.contains('active')
  ) {
    try {
      mirrorGraphFromAnomalyDup();
    } catch (e) {
      console.warn('mirrorGraphFromAnomalyDup', e);
    }
  }
  var g = (document.getElementById('graphSample')?.value || '').trim();
  if (g) return g;
  return (document.getElementById('anomSampleSelect')?.value || '').trim();
}

async function reprocessAnomalyWindow() {
  const plantId = getViewDataPlantId();
  if (!plantId) {
    fireAlert('warning', 'Select a sample', 'Choose Apple (or any sample) in the dropdown above on this tab.', 4000);
    var mh = document.getElementById('mlScanHint');
    if (mh) mh.textContent = 'Pick a sample in the dropdown, then Run ML scan or Reprocess.';
    return;
  }
  const hours =
    typeof coerceGraphHourRange === 'function'
      ? coerceGraphHourRange()
      : parseInt(document.getElementById('graphRange')?.value || '24', 10);
  try {
    const res = await authFetch(API_BASE + '/api/anomalies/reprocess?plant_id=' + encodeURIComponent(plantId) + '&hours=' + encodeURIComponent(String(hours)), { method: 'POST' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const j = await res.json();
    fireAlert('ok', 'Reprocessed', 'Replayed ' + (j.telemetry_rows_reprocessed || 0) + ' telemetry rows for sample #' + plantId + '.', 5000);
    if (typeof fetchTelemetry === 'function') await fetchTelemetry();
    if (typeof fetchAnomalies === 'function') await fetchAnomalies();
  } catch (e) {
    fireAlert('danger', 'Reprocess failed', String(e.message || e), 5000);
  }
}

const ML_COUNT_ORDER = ['normal', 'spike', 'level_shift', 'drift', 'ewma_breach', 'noise', 'dropout', 'missing_data', 'correlation', 'seasonal', 'other'];

function renderMlCountsPanel(payload) {
  const panel = document.getElementById('mlCountsPanel');
  const hintEl = document.getElementById('mlScanHint');
  if (!panel) return;

  const counts = (payload && payload.counts && typeof payload.counts === 'object') ? payload.counts : {};
  const rowsScored = payload && payload.rows_scored != null ? Number(payload.rows_scored) : 0;
  const enabled = !!(payload && payload.ml_enabled !== false && payload.detail !== 'disabled');
  let keys = [...new Set([...ML_COUNT_ORDER, ...Object.keys(counts)])].filter(function (k) {
    return k !== 'detail' && k !== 'enabled';
  });
  keys.sort(function (a, b) {
    const ia = ML_COUNT_ORDER.indexOf(a);
    const ib = ML_COUNT_ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b);
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });

  if (!enabled || payload.detail === 'no_model_file') {
    panel.innerHTML = '<p class="anom-ml-counts-msg">ML classifier unavailable: missing <code>artifacts/anomaly_classifier.joblib</code> or set <code>ML_ANOM_CLASSIFIER_ENABLED=false</code> in backend/.env (see docs/ml-classifier.md).</p>';
    if (hintEl) hintEl.textContent = payload.message || '';
    return;
  }

  const chips = keys.map(function (k) {
    const n = counts[k] != null ? Number(counts[k]) : 0;
    return '<span class="anom-ml-chip" data-mlcls="' + escapeHtml(k) + '">' + escapeHtml(k) + ' <strong>' + n + '</strong></span>';
  }).join('');
  panel.innerHTML =
    '<div class="anom-ml-counts-head">Predicted labels <span class="anom-ml-counts-meta">' + rowsScored + ' rows scored</span></div>' +
    '<div class="anom-ml-chips">' + chips + '</div>';
  if (hintEl) hintEl.textContent = payload.message ? String(payload.message) : '';
}

async function runMlClassifyStoredWindow() {
  var hintEl = document.getElementById('mlScanHint');
  var btn = document.getElementById('mlScanBtn');
  var btnLabel = btn ? btn.textContent : '';
  try {
    var plantRaw = getViewDataPlantId();
    if (!plantRaw) {
      if (hintEl) {
        hintEl.textContent =
          'Select a sample in the dropdown above (e.g. Apple · TM-S001), then click Run ML scan.';
      }
      fireAlert(
        'warning',
        'Select a sample',
        'Use the sample dropdown on this tab — it must not be \"All Samples\".',
        5000,
      );
      return;
    }
    var pidNum = parseInt(String(plantRaw), 10);
    if (!Number.isFinite(pidNum) || pidNum < 1) {
      if (hintEl) hintEl.textContent = 'Invalid sample id — pick a plant from the list again.';
      fireAlert('warning', 'Invalid sample', 'Could not read plant id from the dropdown.', 4000);
      return;
    }
    var hoursEl = document.getElementById('mlScanHours');
    var hours = Math.min(Math.max(parseInt(hoursEl && hoursEl.value ? hoursEl.value : '24', 10) || 24, 1), 720);
    var signal = undefined;
    if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
      signal = AbortSignal.timeout(25000);
    } else if (typeof AbortController !== 'undefined') {
      var ac = new AbortController();
      setTimeout(function () {
        try {
          ac.abort();
        } catch (_) {
          /* ignore */
        }
      }, 25000);
      signal = ac.signal;
    }

    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Scanning…';
    }
    if (hintEl) hintEl.textContent = 'Running…';

    var ep = CONFIG.ENDPOINTS.mlClassifyWindow || '/api/ml/classify/window';
    var res = await authFetch(API_BASE + ep, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plant_id: pidNum, hours }),
      signal: signal,
    });
    var j = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      var detMsg = '';
      if (Array.isArray(j.detail)) {
        detMsg = j.detail
          .map(function (item) {
            if (item && typeof item === 'object' && item.msg != null) return String(item.msg);
            return String(typeof item === 'object' ? JSON.stringify(item) : item);
          })
          .join('; ');
      } else if (j.detail != null) {
        detMsg = typeof j.detail === 'object' ? JSON.stringify(j.detail) : String(j.detail);
      }
      renderMlCountsPanel({ ml_enabled: false, message: '', detail: 'disabled' });
      throw new Error(detMsg || 'HTTP ' + res.status);
    }
    renderMlCountsPanel(j);
    var rows = j.rows_scored != null ? Number(j.rows_scored) : 0;
    if (hintEl && rows === 0) {
      hintEl.textContent =
        '0 rows in this window for sample #' +
        pidNum +
        '. Widen ML hours or the Graphs time range, or ingest / backfill data with plant_id.';
    }
    try {
      var pan = document.getElementById('mlCountsPanel');
      if (pan) pan.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (_) {
      /* ignore */
    }
    fireAlert('ok', 'ML scan', 'Scored ' + rows + ' telemetry rows. (Label chips are directly above.)', 5500);
  } catch (e) {
    console.warn('runMlClassifyStoredWindow failed', e);
    var msg = String(e && e.name === 'AbortError' ? 'Request timed out (25s).' : e.message || e);
    if (hintEl) hintEl.textContent = msg;
    try {
      fireAlert('danger', 'ML scan failed', msg, 6000);
    } catch (_) {
      /* ignore */
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = btnLabel || 'Run ML scan';
    }
  }
}

function anomEventKey(evt) {
  return (evt.timestamp || '') + '|' + (evt.type || '') + '|' + (evt.sensor || '') + '|' + String(evt.description || '').slice(0, 120);
}
function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function loadAnomAckFromStorage() {
  try {
    const raw = localStorage.getItem('terrametric-anom-ack');
    if (raw) anomAckKeys = new Set(JSON.parse(raw));
  } catch (e) { anomAckKeys = new Set(); }
}
function saveAnomAckToStorage() {
  try {
    localStorage.setItem('terrametric-anom-ack', JSON.stringify([...anomAckKeys].slice(-800)));
  } catch (e) {}
}
function anomResetVisible() { anomLogVisible = ANOM_PAGE_SIZE; }
function anomLoadMore() { anomLogVisible += ANOM_PAGE_SIZE; renderAnomalyTable(); }

function anomAcknowledge(key) {
  anomAckKeys.add(key);
  saveAnomAckToStorage();
  renderAnomalyTable();
}
function clearAnomAcknowledgements() {
  if (!anomAckKeys.size) { fireAlert('info', 'Nothing to clear', 'No reviewed marks in this browser.', 2500); return; }
  if (!confirm('Clear all reviewed marks from this browser?')) return;
  anomAckKeys.clear();
  saveAnomAckToStorage();
  renderAnomalyTable();
}
function clearAnomFocus() {
  anomFocusTs = null;
  const bar = document.getElementById('anomFocusBar');
  if (bar) bar.classList.remove('visible');
  renderAnomalyTable();
}
function anomSetFocus(ts) {
  anomFocusTs = ts;
  const bar = document.getElementById('anomFocusBar');
  const lab = document.getElementById('anomFocusLabel');
  if (bar && lab) {
    lab.textContent = 'Focused: ' + new Date(ts).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    bar.classList.add('visible');
  }
  renderAnomalyTable();
}

function initAnomalyBodyDelegateOnce() {
  const body = document.getElementById('anomalyBody');
  if (!body || body.dataset.anomDel) return;
  body.dataset.anomDel = '1';
  body.addEventListener('click', function(ev) {
    const ack = ev.target.closest('[data-anom-ack]');
    if (ack) {
      ev.preventDefault();
      ev.stopPropagation();
      const k = ack.getAttribute('data-anom-ack');
      if (k) anomAcknowledge(decodeURIComponent(k));
      return;
    }
    const foc = ev.target.closest('[data-anom-focus-ts]');
    if (foc) {
      ev.preventDefault();
      ev.stopPropagation();
      anomSetFocus(decodeURIComponent(foc.getAttribute('data-anom-focus-ts') || ''));
      return;
    }
    const fh = ev.target.closest('.anom-group-head');
    if (fh && !ev.target.closest('button')) {
      ev.preventDefault();
      const bodyEl = fh.nextElementSibling;
      if (bodyEl && bodyEl.classList.contains('anom-group-body')) {
        bodyEl.classList.toggle('open');
        const chev = fh.querySelector('.anom-grp-chev');
        if (chev) chev.textContent = bodyEl.classList.contains('open') ? '▾' : '▸';
      }
    }
  });
}

function anomCollectFiltered() {
  const typeF = document.getElementById('anomFilterType')?.value || '';
  const sevF = document.getElementById('anomFilterSev')?.value || '';
  const sensorF = document.getElementById('anomFilterSensor')?.value || '';
  const search = (document.getElementById('anomSearch')?.value || '').trim().toLowerCase();
  let filtered = anomalyLog.slice();
  if (typeF) filtered = filtered.filter(e => e.type === typeF);
  if (sevF) filtered = filtered.filter(e => e.severity === sevF);
  if (sensorF) filtered = filtered.filter(e => e.sensor === sensorF);
  if (search) {
    filtered = filtered.filter(e =>
      (e.type || '').toLowerCase().includes(search) ||
      (e.sensor || '').toLowerCase().includes(search) ||
      (e.description || '').toLowerCase().includes(search)
    );
  }
  if (document.getElementById('anomHideAck')?.checked) {
    filtered = filtered.filter(e => !anomAckKeys.has(anomEventKey(e)));
  }
  filtered.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  return filtered;
}

async function fetchAnomalies() {
  var hintEl = document.getElementById('anomFetchHint');
  if (hintEl) hintEl.textContent = '';
  try {
    const hourRange =
      typeof coerceGraphHourRange === 'function'
        ? coerceGraphHourRange()
        : Math.min(Math.max(parseInt(document.getElementById('graphRange')?.value || '24', 10) || 24, 1), 8760);
    const sampleEl = document.getElementById('graphSample');
    const plantId = sampleEl && sampleEl.value ? String(sampleEl.value).trim() : '';
    let path = CONFIG.ENDPOINTS.anomalies + '?hours=' + encodeURIComponent(String(hourRange));
    if (plantId) path += '&plant_id=' + encodeURIComponent(plantId);
    const d = await apiFetch(path);
    anomalyLog = d.events || [];
    updateAnomalySummaryCards(d);
    renderAnomalyTable();
    if (hintEl && ((d.total ?? 0) === 0)) {
      hintEl.textContent = plantId
        ? ('No persisted FR10 events in this window for sample #' +
            plantId +
            '. Charts can still show telemetry — try Reprocess window, widen the graphs range, or confirm live/dummy ingest includes plant_id.')
        : 'No persisted FR10 events in this window for your samples — pick a sample, widen range, or use Reprocess window.';
    }
    if (document.getElementById('tab-anomalies')?.classList.contains('active')) {
      refreshAnomalyTabCharts(false);
    }
  } catch (e) {
    console.warn('fetchAnomalies failed', e);
    anomalyLog = [];
    updateAnomalySummaryCards({
      total: 0,
      by_type: {},
      by_severity: {},
      spike: 0,
      drift: 0,
      noise: 0,
      dropout: 0,
      correlation: 0,
      level_shift: 0,
      ewma_breach: 0,
      events: [],
    });
    renderAnomalyTable();
    var msg =
      'Could not load anomaly events from the server (check login, API_BASE/port in js/config.js, and that uvicorn is running). ' +
      'Charts may still reflect telemetry.';
    var h = document.getElementById('anomFetchHint');
    if (h) h.textContent = msg;
  }
}

const ANOM_COLORS = { temperature:'#7a8c1e', humidity:'#4a7c8f', light:'#c4711a', height:'#3d5016' };
const ANOM_UNITS  = { temperature:'°C', humidity:'%RH', light:'lux', height:'cm' };
const ANOM_TYPE_META = {
  spike:       { icon:'⚡', color:'#a83232', label:'Spike',        pill:'danger' },
  drift:       { icon:'📈', color:'#4a7c8f', label:'Drift',        pill:'info' },
  noise:       { icon:'🔥', color:'#c4711a', label:'Noise',        pill:'warning' },
  dropout:     { icon:'📉', color:'#8a5000', label:'Dropout',      pill:'warning' },
  correlation: { icon:'🔗', color:'#6a4ca0', label:'Correlation',  pill:'info' },
  level_shift: { icon:'🔀', color:'#2a7a4a', label:'Level Shift',  pill:'danger' },
  ewma_breach: { icon:'📐', color:'#5a6a1a', label:'EWMA Breach',  pill:'warning' },
  seasonal:    { icon:'🌗', color:'#3a6a8a', label:'Seasonal',     pill:'info' },
  missing_data:{ icon:'⬚', color:'#6a5560', label:'Missing Data', pill:'warning' },
};
function updateAnomalySummaryCards(d) {
  setText('anomTotal',      d.total ?? 0);
  setText('anomSpike',      d.spike ?? d.by_type?.spike ?? 0);
  setText('anomDrift',      d.drift ?? d.by_type?.drift ?? 0);
  setText('anomNoise',      d.noise ?? d.by_type?.noise ?? 0);
  setText('anomDropout',    d.dropout ?? d.by_type?.dropout ?? 0);
  setText('anomCorrelation',d.correlation ?? d.by_type?.correlation ?? 0);
  setText('anomLevelShift', d.level_shift ?? d.by_type?.level_shift ?? 0);
  setText('anomEwma',       d.ewma_breach ?? d.by_type?.ewma_breach ?? 0);

  const sevBar = document.getElementById('anomSevBar');
  const countsEl = document.getElementById('anomSevCounts');
  const inner = document.getElementById('anomSevBarInner');
  if (!sevBar || !countsEl || !inner) return;

  const bySev = d.by_severity || {};
  const total = d.total || 0;
  if (total > 0) {
    sevBar.classList.add('is-visible');
    const danger = bySev.danger || 0, warning = bySev.warning || 0, info = bySev.info || 0;
    countsEl.textContent = danger + ' critical · ' + warning + ' warning · ' + info + ' info';
    inner.innerHTML = '';
    if (danger)  inner.innerHTML += '<div class="anom-sev-stack__seg anom-sev-stack__seg--danger" style="flex:' + danger + ' 1 0" title="Critical: ' + danger + '"></div>';
    if (warning) inner.innerHTML += '<div class="anom-sev-stack__seg anom-sev-stack__seg--warning" style="flex:' + warning + ' 1 0" title="Warning: ' + warning + '"></div>';
    if (info)    inner.innerHTML += '<div class="anom-sev-stack__seg anom-sev-stack__seg--info" style="flex:' + info + ' 1 0" title="Info: ' + info + '"></div>';
  } else {
    sevBar.classList.remove('is-visible');
  }
}

function resetAnomalySummaryCards() {
  for (const id of ['anomTotal','anomSpike','anomDrift','anomNoise','anomDropout','anomCorrelation','anomLevelShift','anomEwma']) setText(id, '--');
  const sevBar = document.getElementById('anomSevBar');
  if (sevBar) sevBar.classList.remove('is-visible');
}

function buildAnomSensorPills() {
  const container = document.getElementById('anomSensorPills');
  if (!container) return;
  const available = new Set();
  for (const r of anomSimReadings) {
    for (const k of ['temperature','humidity','light','height']) { if (r[k] != null) available.add(k); }
  }
  container.innerHTML = '';
  for (const s of available) {
    const pill = document.createElement('button');
    pill.className = 'plant-tab' + (anomSimActiveSensors.has(s) ? ' active' : '');
    pill.textContent = s.charAt(0).toUpperCase() + s.slice(1);
    pill.onclick = () => {
      anomSimActiveSensors.has(s) ? anomSimActiveSensors.delete(s) : anomSimActiveSensors.add(s);
      pill.classList.toggle('active');
      refreshAnomalyTabCharts(true);
    };
    container.appendChild(pill);
  }
}

function renderAnomCharts() {
  const wrap = document.getElementById('anomChartWrap');
  if (!anomSimReadings.length) return;

  const showMarkers = document.getElementById('anomShowMarkers')?.checked ?? true;
  const activeSensors = [...anomSimActiveSensors].filter(s => anomSimReadings.some(r => r[s] != null));
  if (!activeSensors.length) { wrap.innerHTML = '<div class="anom-placeholder anom-placeholder--compact"><p class="anom-placeholder__text">Select at least one sensor channel in the toolbar above.</p></div>'; return; }

  if (charts.anomSim) { for (const c of Object.values(charts.anomSim)) { if (c && c.destroy) c.destroy(); } }
  charts.anomSim = {};

  let html = '';
  for (const sensor of activeSensors) {
    html += '<div style="margin-bottom:6px;"><canvas id="anomChart_' + sensor + '" height="' + (activeSensors.length > 1 ? 100 : 180) + '"></canvas></div>';
  }
  wrap.innerHTML = html;

  for (const sensor of activeSensors) {
    const linePts = [];
    for (let pi = 0; pi < anomSimReadings.length; pi++) {
      const r = anomSimReadings[pi];
      const x = anomTimestampToMs(r.timestamp);
      if (!Number.isFinite(x)) continue;
      linePts.push({ x: x, y: r[sensor] });
    }

    if (!linePts.length) continue;

    let xMin = Infinity;
    let xMax = -Infinity;
    for (let li = 0; li < linePts.length; li++) {
      const xv = linePts[li].x;
      if (xv < xMin) xMin = xv;
      if (xv > xMax) xMax = xv;
    }

    const datasets = [
      {
        type: 'line',
        label: sensor.charAt(0).toUpperCase() + sensor.slice(1) + ' (' + (ANOM_UNITS[sensor] || '') + ')',
        order: 0,
        data: linePts,
        borderColor: ANOM_COLORS[sensor],
        backgroundColor: ANOM_COLORS[sensor] + '18',
        borderWidth: 1.5,
        tension: 0.3,
        fill: true,
        pointRadius: showMarkers ? 0.55 : 0,
        pointHoverRadius: showMarkers ? 4 : 0,
        pointBackgroundColor: ANOM_COLORS[sensor] + '88',
      },
    ];

    if (showMarkers && anomalyLog.length) {
      const sensorEvents = anomalyLog.filter(function (e) { return anomalyEventMatchesSensor(e, sensor); });
      const byType = {};
      for (let si = 0; si < sensorEvents.length; si++) {
        const e = sensorEvents[si];
        const tk = String(e.type || '').toLowerCase();
        (byType[tk] = byType[tk] || []).push(e);
      }
      for (const [typeKey, evts] of Object.entries(byType)) {
        const pts = [];
        for (let j = 0; j < evts.length; j++) {
          const e = evts[j];
          const xEv = anomTimestampToMs(e.timestamp);
          if (!Number.isFinite(xEv)) continue;
          if (xEv < xMin || xEv > xMax) continue;
          const pt = anomInterpolateReadingPointAt(sensor, xEv);
          if (!pt) continue;
          pts.push(pt);
        }
        if (!pts.length) continue;
        const meta = ANOM_TYPE_META[typeKey] || { color: '#6a5560', label: typeKey };
        datasets.push({
          type: 'scatter',
          order: 20,
          clip: false,
          label: meta.label,
          data: pts,
          pointStyle: 'triangle',
          pointRadius: 7,
          hitRadius: 10,
          pointBorderWidth: 2,
          pointBorderColor: meta.color,
          pointBackgroundColor: meta.color + 'cc',
          showLine: false,
        });
      }
    }

    charts.anomSim[sensor] = new Chart(document.getElementById('anomChart_' + sensor), {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        animation: { duration: 300 },
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        plugins: {
          legend: { labels: { font: { family: 'DM Mono', size: 9 }, usePointStyle: true, padding: 10 } },
          tooltip: {
            backgroundColor: '#2c2a1e',
            titleFont: { family: 'Syne', weight: '700' },
            bodyFont: { family: 'DM Mono', size: 10 },
            cornerRadius: 8,
            padding: 8,
            callbacks: {
              title: function (items) {
                const item = items[0];
                if (!item) return '';
                let x = item.parsed && item.parsed.x != null ? item.parsed.x : null;
                if (x == null && item.raw && typeof item.raw === 'object') x = item.raw.x;
                if (!Number.isFinite(Number(x))) return '';
                var dt = new Date(Number(x));
                return isNaN(dt.getTime())
                  ? String(x)
                  : dt.toLocaleString([], {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    });
              },
              afterBody: function (ctx) {
                const item = ctx[0];
                if (!item) return '';
                let t0 = NaN;
                if (item.parsed && item.parsed.x != null && Number.isFinite(Number(item.parsed.x))) {
                  t0 = Number(item.parsed.x);
                } else if (item.raw && typeof item.raw === 'object' && item.raw.x != null) {
                  t0 = Number(item.raw.x);
                }
                if (!Number.isFinite(t0)) return '';
                var maxW = anomTooltipMatchWindowMs();
                var evNear = anomalyLog.filter(function (e) {
                  if (!anomalyEventMatchesSensor(e, sensor)) return false;
                  var ta = new Date(e.timestamp).getTime();
                  return Number.isFinite(ta) && Math.abs(ta - t0) <= maxW;
                });
                if (!evNear.length) return '';
                evNear.sort(function (a, b) {
                  var da = Math.abs(new Date(a.timestamp).getTime() - t0);
                  var db = Math.abs(new Date(b.timestamp).getTime() - t0);
                  return da - db;
                });
                var LIMIT = 10;
                var lines = [];
                var n = Math.min(evNear.length, LIMIT);
                for (var ii = 0; ii < n; ii++) {
                  var ee = evNear[ii];
                  lines.push(
                    (ANOM_TYPE_META[String(ee.type || '').toLowerCase()]?.icon || '') +
                      ' ' +
                      ee.type +
                      ': ' +
                      (ee.description || '').slice(0, 72),
                  );
                }
                var tail = '';
                if (evNear.length > LIMIT) tail = '\n… and ' + (evNear.length - LIMIT) + ' more in this vicinity';
                return '\n--- Anomalies ---\n' + lines.join('\n') + tail;
              },
            },
          },
          zoom: {
            pan: { enabled: true, mode: 'x' },
            zoom: {
              wheel: { enabled: true },
              pinch: { enabled: true },
              drag: { enabled: false },
              mode: 'x',
            },
            limits: { x: { minRange: ANOM_ZOOM_X_MIN_MS } },
          },
        },
        scales: {
          x: {
            type: 'linear',
            ticks: {
              font: { family: 'DM Mono', size: 8 },
              maxTicksLimit: 12,
              callback: function (value) {
                return new Date(value).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                  month: 'short',
                  day: 'numeric',
                });
              },
            },
            grid: { display: false },
          },
          y: {
            title: {
              display: true,
              text: sensor.charAt(0).toUpperCase() + sensor.slice(1) + ' (' + (ANOM_UNITS[sensor] || '') + ')',
              font: { family: 'Syne', size: 10, weight: '700' },
            },
            ticks: { font: { family: 'DM Mono', size: 9 } },
            grid: { color: '#e8e3d0' },
          },
        },
      },
    });
  }
}

function renderAnomalyScoreTimeline() {
  const wrap = document.getElementById('anomScoreWrap');
  if (!wrap) return;
  if (!anomSimReadings.length || !anomalyLog.length) { wrap.innerHTML = '<div class="anom-placeholder anom-placeholder--compact"><p class="anom-placeholder__text">No scored anomalies for this run.</p></div>'; return; }

  if (charts.anomScore) charts.anomScore.destroy();
  wrap.innerHTML = '<canvas id="anomScoreChart" height="80"></canvas>';

  const scorePts = [];
  for (let i = 0; i < anomSimReadings.length; i++) {
    const r = anomSimReadings[i];
    const x = anomTimestampToMs(r.timestamp);
    if (!Number.isFinite(x)) continue;
    const evts = anomEventsNearReadingTs(r.timestamp);
    let score = 0;
    for (const e of evts) { score += e.severity === 'danger' ? 3 : e.severity === 'warning' ? 2 : 1; }
    scorePts.push({ x, y: score, __ts: r.timestamp });
  }

  const gradient = document.getElementById('anomScoreChart').getContext('2d');
  const g = gradient.createLinearGradient(0,0,0,80);
  g.addColorStop(0,'rgba(168,50,50,0.6)'); g.addColorStop(1,'rgba(168,50,50,0.02)');

  charts.anomScore = new Chart(document.getElementById('anomScoreChart'), {
    type: 'bar',
    data: {
      datasets: [{
        label: 'Anomaly Score',
        data: scorePts,
        backgroundColor: g,
        borderColor: 'rgba(168,50,50,0.7)',
        borderWidth: 1,
        borderRadius: 2,
        parsing: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: { duration: 300 },
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#2c2a1e',
          bodyFont: { family: 'DM Mono', size: 10 },
          cornerRadius: 6,
          callbacks: {
            label: ctx => {
              const xv = ctx.parsed && ctx.parsed.x != null ? ctx.parsed.x : null;
              let ts = ctx.raw && typeof ctx.raw === 'object' && ctx.raw.__ts != null ? ctx.raw.__ts : null;
              if (!ts && Number.isFinite(xv)) {
                const p = scorePts.find(pt => pt.x === xv);
                ts = p && p.__ts;
              }
              const n = ts ? anomEventsNearReadingTs(ts).length : 0;
              const y = ctx.parsed && ctx.parsed.y != null ? ctx.parsed.y : (ctx.raw && ctx.raw.y);
              return 'Score: ' + y + ' (' + n + ' events)';
            },
          },
        },
        zoom: {
          pan: { enabled: true, mode: 'x' },
          zoom: {
            wheel: { enabled: true },
            pinch: { enabled: true },
            drag: { enabled: false },
            mode: 'x',
          },
          limits: { x: { minRange: ANOM_ZOOM_X_MIN_MS } },
        },
      },
      scales: {
        x: { type: 'linear', display: false, grid: { display: false } },
        y: { beginAtZero: true, ticks: { font: { family: 'DM Mono', size: 9 }, stepSize: 1 }, grid: { color: '#e8e3d033' } },
      },
    },
  });
}

function renderAnomalyTable() {
  initAnomalyBodyDelegateOnce();
  loadAnomAckFromStorage();

  const filtered = anomCollectFiltered();
  const groupBy = document.getElementById('anomGroupByTime')?.checked;
  const body = document.getElementById('anomalyBody');
  if (!body) return;

  const countLabel = filtered.length
    ? ('(' + filtered.length + (filtered.length !== anomalyLog.length ? ' filtered' : '') + ')')
    : '';
  const logCount = document.getElementById('anomLogCount');
  if (logCount) logCount.textContent = countLabel;

  if (!filtered.length) {
    const emptyRegister =
      !anomalyLog.length
        ? 'No anomaly events in this window. That can mean none were detected yet, no telemetry rows for this sample and range, rows lack plant_id (see banner above), or the backend could not load events.'
        : 'No events match the current filters.';
    body.innerHTML = '<div class="anom-placeholder"><span class="anom-placeholder__glyph" aria-hidden="true">◇</span><p class="anom-placeholder__text">' + emptyRegister + '</p></div>';
    return;
  }

  let html = '';
  let hasMore = false;
  let totalClusters = 0;

  if (groupBy) {
    const map = new Map();
    for (const e of filtered) {
      if (!map.has(e.timestamp)) map.set(e.timestamp, []);
      map.get(e.timestamp).push(e);
    }
    const clusters = [...map.entries()].sort((a, b) => new Date(b[0]) - new Date(a[0]));
    totalClusters = clusters.length;
    let n = 0;
    for (const [ts, evts] of clusters) {
      if (n >= anomLogVisible) { hasMore = true; break; }
      n++;
      const types = [...new Set(evts.map(x => x.type))].join(', ');
      const encTs = encodeURIComponent(ts);
      const openCls = anomFocusTs === ts ? ' open' : '';
      const chev = anomFocusTs === ts ? '▾' : '▸';
      html += '<div class="anom-group"><div class="anom-group-head">';
      html += '<span class="anom-grp-chev" style="font-size:12px;color:var(--bark-mid);width:18px;">' + chev + '</span>';
      html += '<span style="flex:1;font-family:\'DM Mono\',monospace;font-size:10px;">' + escapeHtml(new Date(ts).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })) + '</span>';
      html += '<span class="anom-group-meta">' + evts.length + ' · ' + escapeHtml(types) + '</span>';
      html += '<button type="button" class="btn btn-ghost" style="font-size:9px;padding:3px 8px;" data-anom-focus-ts="' + encTs + '">Focus</button>';
      html += '</div><div class="anom-group-body' + openCls + '">';
      for (const a of evts) {
        const meta = ANOM_TYPE_META[a.type] || { pill: 'info', label: a.type };
        const key = anomEventKey(a);
        const encKey = encodeURIComponent(key);
        const reviewed = anomAckKeys.has(key);
        html += '<div class="anom-mini-row">';
        html += '<span><span class="sev-pill ' + meta.pill + '" style="text-transform:uppercase;font-size:7px;">' + escapeHtml(meta.label) + '</span> ' + escapeHtml((a.description || '').slice(0, 72)) + (a.description && a.description.length > 72 ? '…' : '') + '</span>';
        html += '<span><span class="sev-pill ' + (a.severity || 'info') + '">' + escapeHtml((a.severity || '').toUpperCase()) + '</span></span>';
        html += '<span style="font-size:9px;color:var(--bark-mid);">' + escapeHtml(a.sensor || '—') + '</span>';
        html += '<span style="display:flex;gap:4px;justify-content:flex-end;">';
        html += '<button type="button" class="btn btn-ghost" style="font-size:8px;padding:2px 6px;" data-anom-ack="' + encKey + '"' + (reviewed ? ' disabled="disabled"' : '') + '>' + (reviewed ? '✓' : 'Review') + '</button>';
        html += '<button type="button" class="btn btn-ghost" style="font-size:8px;padding:2px 6px;" data-anom-focus-ts="' + encTs + '">→</button>';
        html += '</span></div>';
        html += '<div style="padding:0 0 10px 4px;font-size:10px;color:var(--bark-mid);">' + buildDetailPanel(a) + '</div>';
      }
      html += '</div></div>';
    }
  } else {
    const slice = filtered.slice(0, anomLogVisible);
    hasMore = filtered.length > anomLogVisible;
    slice.forEach((a, idx) => {
      const meta = ANOM_TYPE_META[a.type] || { pill: 'info', label: a.type, icon: '?' };
      const detailHtml = buildDetailPanel(a);
      const key = anomEventKey(a);
      const encKey = encodeURIComponent(key);
      const encTs = encodeURIComponent(a.timestamp);
      const reviewed = anomAckKeys.has(key);
      const focusCls = anomFocusTs === a.timestamp ? ' anom-row-focus' : '';
      html += '<div class="tbl-row' + focusCls + '" style="grid-template-columns:30px 130px 90px 100px 1fr 72px 62px;cursor:pointer;" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'\':\'none\'">';
      html += '<span style="font-size:12px;color:var(--bark-mid);">▸</span>';
      html += '<span style="font-size:10px;">' + escapeHtml(new Date(a.timestamp).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })) + '</span>';
      html += '<span><span class="sev-pill ' + meta.pill + '" style="text-transform:uppercase;">' + escapeHtml(meta.label) + '</span></span>';
      html += '<span style="font-size:10px;">' + escapeHtml(a.sensor || '—') + '</span>';
      html += '<span style="font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + escapeHtml(a.description || '') + '</span>';
      html += '<span><span class="sev-pill ' + (a.severity || 'info') + '">' + escapeHtml((a.severity || '').toUpperCase()) + '</span></span>';
      html += '<span style="font-size:9px;color:var(--bark-mid);">' + (reviewed ? 'Reviewed' : '—') + '</span>';
      html += '</div>';
      html += '<div style="display:none;padding:12px 20px 16px 46px;background:#faf8f0;border-bottom:1px solid var(--cream-dark);font-size:10px;line-height:1.7;">';
      html += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">';
      html += '<button type="button" class="btn btn-ghost" style="font-size:9px;padding:4px 10px;" data-anom-focus-ts="' + encTs + '">Focus this time</button>';
      html += '<button type="button" class="btn btn-ghost" style="font-size:9px;padding:4px 10px;" data-anom-ack="' + encKey + '"' + (reviewed ? ' disabled="disabled"' : '') + '>' + (reviewed ? 'Already reviewed' : 'Mark reviewed') + '</button>';
      html += '</div>' + detailHtml + '</div>';
    });
  }

  if (hasMore) {
    html += '<div class="anom-load-more-wrap"><button type="button" class="btn btn-primary" style="font-size:10px;padding:6px 18px;" onclick="anomLoadMore()">Load more</button>';
    const sub = groupBy && totalClusters
      ? ('Showing ' + Math.min(anomLogVisible, totalClusters) + ' of ' + totalClusters + ' time buckets')
      : ('Showing ' + Math.min(anomLogVisible, filtered.length) + ' of ' + filtered.length + ' events');
    html += '<span style="display:block;margin-top:6px;font-size:9px;color:var(--bark-mid);">' + sub + '</span></div>';
  }

  body.innerHTML = html;
}

function buildDetailPanel(event) {
  const d = event.detail;
  if (!d || !Object.keys(d).length) return '<span style="color:var(--bark-mid);">No additional detail available.</span>';

  let rows = '';
  const labelMap = {
    z_score:'Z-Score', value:'Value', mean:'Mean', std:'Std Dev',
    slope:'Slope', r_squared:'R²', direction:'Direction',
    cusum:'CUSUM', threshold_h:'Threshold (h)', allowance_k:'Allowance (k)', shift_magnitude:'Shift Size',
    pearson_r:'Pearson r', abs_r:'|r|', window_size:'Window',
    ewma:'EWMA', ucl:'UCL', lcl:'LCL', sigma:'σ', deviation_sigma:'Deviation (σ)',
    lambda:'Lambda (λ)', L:'L multiplier',
    expected_mean:'Expected', expected_std:'Expected σ', hour:'Hour',
    gap_seconds:'Gap (sec)', expected_interval:'Expected Interval', lower_bound:'Lower Bound', upper_bound:'Upper Bound',
    reason:'Reason',
  };
  for (const [k, v] of Object.entries(d)) {
    const label = labelMap[k] || k.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
    let val;
    if (typeof v === 'number') {
      val = Number.isFinite(v) ? (Number.isInteger(v) ? String(v) : v.toFixed(4)) : String(v);
    } else {
      val = escapeHtml(String(v));
    }
    rows += '<div style="display:flex;gap:12px;"><span style="color:var(--bark-mid);min-width:120px;">' + escapeHtml(label) + '</span><span style="font-family:\'DM Mono\',monospace;font-weight:600;">' + val + '</span></div>';
  }
  return rows;
}

function exportAnomalyCSV() {
  if (!anomalyLog.length) {
    fireAlert('warning', 'No Data', 'Load live persisted events from the API (ingest / reprocess window) first.', 3000);
    return;
  }
  const header = 'Timestamp,Type,Sensor,Description,Severity,Status';
  const rows = anomalyLog.map(e => {
    const desc = (e.description == null ? '' : String(e.description)).replace(/"/g,'""');
    return `"${e.timestamp}","${e.type}","${e.sensor}","${desc}","${e.severity}","${e.status||'active'}"`;
  });
  downloadFile('terrametric-anomalies.csv', [header, ...rows].join('\n'), 'text/csv');
}

function printAnomalyReport() {
  if (!anomalyLog.length) {
    fireAlert('warning', 'No Data', 'Load live persisted events from the API first.', 3000);
    return;
  }
  const w = window.open('', '_blank');
  const sample = document.getElementById('graphSample')?.value || '';
  let html =
    '<html><head><title>TerraMetric Anomaly Report</title><style>body{font-family:Arial,sans-serif;padding:40px;color:#333;}h1{font-size:18px;}table{border-collapse:collapse;width:100%;margin-top:16px;font-size:11px;}th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;}th{background:#f5f0e0;}.badge{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:bold;}.danger{background:#ffe0e0;color:#8a1010;}.warning{background:#fff0c0;color:#8a5000;}.info{background:#e0f0ff;color:#204060;}</style></head><body>';
  html += '<h1>TerraMetric Anomaly Detection Report</h1>';
  html +=
    '<p style="font-size:12px;color:#666;">Sample: <strong>' +
    escapeHtml(sample ? '#' + sample : 'all combined') +
    '</strong> · Generated: ' +
    new Date().toLocaleString() +
    ' · Total events: ' +
    anomalyLog.length +
    '</p>';
  html += '<table><tr><th>Time</th><th>Type</th><th>Sensor</th><th>Description</th><th>Severity</th></tr>';
  for (const e of anomalyLog) {
    const sev = (e.severity || 'info');
    const badgeClass = (sev === 'danger' || sev === 'warning' || sev === 'info') ? sev : 'info';
    html += '<tr><td>' + escapeHtml(new Date(e.timestamp).toLocaleString()) + '</td><td>' + escapeHtml(e.type) + '</td><td>' + escapeHtml(e.sensor) + '</td><td>' + escapeHtml(e.description || '') + '</td><td><span class="badge ' + badgeClass + '">' + escapeHtml(String(sev).toUpperCase()) + '</span></td></tr>';
  }
  html += '</table></body></html>';
  w.document.write(html);
  w.document.close();
  w.print();
}

loadAnomAckFromStorage();
initAnomalyBodyDelegateOnce();
updateAnomDataSourceBanner();

window.addEventListener('samples:changed', function () {
  void (async function () {
    if (typeof fetchTelemetry === 'function' && document.getElementById('tab-anomalies')?.classList.contains('active')) {
      await fetchTelemetry();
    } else if (typeof fetchAnomalies === 'function') {
      fetchAnomalies();
    }
    if (typeof refreshAnomalyPlantIdSessionHint === 'function' && document.getElementById('tab-anomalies')?.classList.contains('active')) {
      refreshAnomalyPlantIdSessionHint();
    }
  })();
});

window.runMlClassifyStoredWindow = runMlClassifyStoredWindow;
window.renderMlCountsPanel = renderMlCountsPanel;
window.refreshAnomalyTabCharts = refreshAnomalyTabCharts;
