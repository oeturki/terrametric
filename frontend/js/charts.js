// ─────────────────────────────────────────────
//  charts.js — Researcher-grade telemetry charts
//
//  Responsibilities:
//    * Render the four primary sensor charts on the View Data → Graphs tab (linear x = time ms).
//    * Display modes per card (line / area / bar / scatter) + cosmetic style presets + optional MA overlay.
//    * Render Home mini-chart on the same telemetry buffer.
//    * Annotate graphs from tolerance inputs plus an optional plant height goal line.
//    * Zoom/pan via chartjs-plugin-zoom; calendar heatmap for hourly patterns by day.
//
//  Data shape consumed:
//    readings = [{timestamp, temperature, humidity, light, height}, …]
// ─────────────────────────────────────────────

let charts = {};
const HIST = { temp: [], hum: [], light: [], height: [], labels: [], timestamps: [] };

/** Last raw readings from updateCharts(); used to restyle without another telemetry fetch. */
let lastChartReadings = null;

const READING_FIELD = { temp: 'temperature', hum: 'humidity', light: 'light', height: 'height' };

/** Warn when raw bar charts exceed this point count across any card */
const GRAPH_BAR_DENSITY_HINT_AFTER = 80;
const ZOOM_X_MIN_MS = 60 * 1000;

const DEFAULT_GRAPH_VIZ = 'smooth_filled';
const VALID_GRAPH_VIZ_PRESETS = new Set(['smooth_filled', 'outline', 'step', 'straight', 'points', 'area_emphasis']);
const GRAPH_VIZ_SELECT_IDS = { temp: 'graphVizTemp', hum: 'graphVizHum', light: 'graphVizLight', height: 'graphVizHeight' };
/** Element id → sensor key */
const GRAPH_VIZ_SELECT_ID_TO_KEY = Object.fromEntries(
  Object.keys(GRAPH_VIZ_SELECT_IDS).map(k => [GRAPH_VIZ_SELECT_IDS[k], k]),
);
const GRAPH_VIZ_STORAGE_PREFIX = 'terrametric-graph-viz-';

const DEFAULT_DISPLAY_MODE = 'line';
const VALID_DISPLAY_MODES = new Set(['line', 'area', 'bar', 'scatter']);
const GRAPH_DISPLAY_IDS = {
  temp: 'graphDisplayTemp',
  hum: 'graphDisplayHum',
  light: 'graphDisplayLight',
  height: 'graphDisplayHeight',
};
const GRAPH_DISPLAY_ID_TO_KEY = Object.fromEntries(
  Object.keys(GRAPH_DISPLAY_IDS).map(k => [GRAPH_DISPLAY_IDS[k], k]),
);
const GRAPH_DISPLAY_STORAGE_PREFIX = 'terrametric-graph-display-';

if (typeof Chart !== 'undefined' && typeof window !== 'undefined') {
  if (window.ChartZoom) Chart.register(window.ChartZoom);
  if (window.ChartAnnotation) Chart.register(window.ChartAnnotation);
}

const SENSOR_META = {
  temp:   { color: '#7a8c1e', unit: '\u00b0C',  label: 'Temperature', warnId: 'warn-temp-high',   warnDir: 'high' },
  hum:    { color: '#4a7c8f', unit: '%',        label: 'Humidity',    warnId: 'warn-hum-high',    warnDir: 'high' },
  light:  { color: '#c4711a', unit: ' lux',     label: 'Light',       warnId: 'warn-light-low',  warnDir: 'low'  },
  height: { color: '#3d5016', unit: ' cm',      label: 'Plant height', warnId: null, goalId: 'height-target', warnDir: null },
};

// ── Parsing & series helpers ───────────────────

function _parseTsMs(timestamp) {
  if (timestamp == null) return NaN;
  const u = typeof timestamp === 'number' && Number.isFinite(timestamp) ? timestamp : Date.parse(String(timestamp));
  return Number.isFinite(u) ? u : NaN;
}

function _zipXY(timesMs, yVals) {
  const out = [];
  const n = Math.min(timesMs.length, yVals.length);
  for (let i = 0; i < n; i++) {
    const x = timesMs[i];
    if (!Number.isFinite(x)) continue;
    const y = yVals[i];
    if (y == null || Number.isNaN(Number(y))) continue;
    out.push({ x, y: Number(y) });
  }
  return out;
}

function _rollingMeanY(yVals, halfWindow) {
  const hw = Math.max(1, Math.min(halfWindow, 60));
  const n = yVals.length;
  const out = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    let sum = 0;
    let c = 0;
    const lo = Math.max(0, i - hw);
    const hi = Math.min(n - 1, i + hw);
    for (let j = lo; j <= hi; j++) {
      const v = yVals[j];
      if (v == null || Number.isNaN(Number(v))) continue;
      sum += Number(v);
      c++;
    }
    out[i] = c ? sum / c : null;
  }
  return out;
}

function _timesMsAlignedWithHist() {
  return HIST.timestamps.map(ts => _parseTsMs(ts));
}

function _movingAvgOverlayEnabled() {
  const cb = typeof document !== 'undefined' ? document.getElementById('graphMovingAvg') : null;
  return !!(cb && cb.checked);
}

// ── Pure stats ───────────────────────────────

function _computeStats(arr) {
  const v = arr.filter(x => x != null && !Number.isNaN(x));
  if (!v.length) return null;
  const sorted = [...v].sort((a, b) => a - b);
  const sum = v.reduce((a, b) => a + b, 0);
  const mean = sum / v.length;
  const median = sorted.length % 2
    ? sorted[(sorted.length - 1) >> 1]
    : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  let variance = 0;
  for (let i = 0; i < v.length; i++) variance += (v[i] - mean) ** 2;
  variance /= v.length;
  return {
    min: sorted[0], max: sorted[sorted.length - 1], mean, median,
    stddev: Math.sqrt(variance), n: v.length, last: arr[arr.length - 1],
  };
}

function _renderStatsPanel(targetId, stats, unit, threshold, warnDir, mode) {
  mode = mode || 'warn';
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!stats) { el.innerHTML = '<div style="font-size:11px;color:var(--bark-mid);">No data in window.</div>'; return; }
  const fmt = (v) => v == null ? '--' : (Number(v).toFixed(2) + unit);
  let lastClass = '';
  if (threshold != null && stats.last != null) {
    if (mode === 'goal') {
      if (stats.last >= threshold) lastClass = 'met';
    } else if (warnDir === 'high') {
      const breached = stats.last >= threshold;
      if (breached) lastClass = 'over';
    } else if (warnDir === 'low') {
      const breached = stats.last <= threshold;
      if (breached) lastClass = 'over';
    }
  }
  const lbl = mode === 'goal' ? 'Goal ref.' : 'Threshold';
  let thrDisp = '--';
  if (threshold != null) {
    if (mode === 'goal') thrDisp = Number(threshold).toFixed(2) + unit + ' (goal)';
    else thrDisp = threshold + unit + ' ' + (warnDir === 'high' ? '\u25b2' : '\u25bc');
  }
  el.innerHTML = '' +
    '<div class="gm"><div class="gm-label">Min</div><div class="gm-val">'    + fmt(stats.min) + '</div></div>' +
    '<div class="gm"><div class="gm-label">Max</div><div class="gm-val">'    + fmt(stats.max) + '</div></div>' +
    '<div class="gm"><div class="gm-label">Mean</div><div class="gm-val">'   + fmt(stats.mean) + '</div></div>' +
    '<div class="gm"><div class="gm-label">Median</div><div class="gm-val">' + fmt(stats.median) + '</div></div>' +
    '<div class="gm"><div class="gm-label">\u03c3</div><div class="gm-val">'  + fmt(stats.stddev) + '</div></div>' +
    '<div class="gm"><div class="gm-label">n</div><div class="gm-val">'      + stats.n + '</div></div>' +
    '<div class="gm"><div class="gm-label">Last</div><div class="gm-val ' + lastClass + '">' + fmt(stats.last) + '</div></div>' +
    '<div class="gm"><div class="gm-label">' + lbl + '</div><div class="gm-val">' + thrDisp + '</div></div>';
}

function _readThresholds() {
  const out = {};
  Object.keys(SENSOR_META).forEach(k => {
    const wid = SENSOR_META[k].warnId;
    if (!wid) {
      out[k] = null;
      return;
    }
    const raw = document.getElementById(wid);
    const parsed = raw ? parseFloat(raw.value) : NaN;
    out[k] = Number.isFinite(parsed) ? parsed : null;
  });
  return out;
}

function _buildAnnotation(threshold, dir) {
  if (threshold == null) return null;
  return {
    type: 'box',
    yMin: dir === 'high' ? threshold : Number.NEGATIVE_INFINITY,
    yMax: dir === 'high' ? Number.POSITIVE_INFINITY : threshold,
    backgroundColor: 'rgba(184, 57, 43, 0.10)',
    borderColor: 'rgba(184, 57, 43, 0.55)',
    borderWidth: 1,
    borderDash: [4, 3],
    label: {
      display: true,
      content: (dir === 'high' ? '> ' : '< ') + threshold,
      position: dir === 'high' ? 'start' : 'end',
      backgroundColor: 'rgba(184, 57, 43, 0.85)',
      color: '#fff',
      font: { size: 9, family: 'DM Mono' },
      padding: 2,
    },
  };
}

function _buildGoalLineAnnotation(goalCm) {
  if (goalCm == null || !Number.isFinite(goalCm)) return null;
  return {
    type: 'line',
    yMin: goalCm,
    yMax: goalCm,
    borderColor: 'rgba(52, 88, 40, 0.92)',
    borderWidth: 2,
    borderDash: [6, 5],
    label: {
      display: true,
      content: 'Goal ' + goalCm + ' cm',
      position: 'center',
      backgroundColor: 'rgba(52, 88, 40, 0.92)',
      color: '#fdfcf7',
      font: { size: 9, family: 'DM Mono' },
      padding: { x: 6, y: 2 },
    },
  };
}

function _syncGraphVizSelectsFromStorage() {
  Object.keys(GRAPH_VIZ_SELECT_IDS).forEach(k => {
    const sel = document.getElementById(GRAPH_VIZ_SELECT_IDS[k]);
    if (!sel) return;
    let stored = null;
    try { stored = sessionStorage.getItem(GRAPH_VIZ_STORAGE_PREFIX + k); } catch (e) { /* ignore */ }
    if (stored && VALID_GRAPH_VIZ_PRESETS.has(stored)) sel.value = stored;
  });
}

function _syncGraphDisplaySelectsFromStorage() {
  Object.keys(GRAPH_DISPLAY_IDS).forEach(k => {
    const sel = document.getElementById(GRAPH_DISPLAY_IDS[k]);
    if (!sel) return;
    let stored = null;
    try { stored = sessionStorage.getItem(GRAPH_DISPLAY_STORAGE_PREFIX + k); } catch (e) { /* ignore */ }
    if (stored && VALID_DISPLAY_MODES.has(stored)) sel.value = stored;
  });
}

/** Cosmetic line style for line/bar roots; area mode forces fill on. */
function _datasetStyleFromPreset(preset, hexColor) {
  const pale = hexColor + '22';
  const bold = hexColor + '55';
  const base = { borderColor: hexColor, spanGaps: true };
  switch (preset) {
    case 'outline':
      return Object.assign({}, base, {
        backgroundColor: 'transparent',
        borderWidth: 2,
        tension: 0.3,
        stepped: false,
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 4,
      });
    case 'step':
      return Object.assign({}, base, {
        backgroundColor: pale,
        borderWidth: 2,
        tension: 0,
        stepped: 'before',
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 4,
      });
    case 'straight':
      return Object.assign({}, base, {
        backgroundColor: pale,
        borderWidth: 2,
        tension: 0,
        stepped: false,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 4,
      });
    case 'points':
      return Object.assign({}, base, {
        backgroundColor: pale,
        borderWidth: 2,
        tension: 0.3,
        stepped: false,
        fill: true,
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBackgroundColor: hexColor,
        pointBorderColor: '#fff',
        pointBorderWidth: 1,
      });
    case 'area_emphasis':
      return Object.assign({}, base, {
        backgroundColor: bold,
        borderWidth: 3,
        tension: 0.3,
        stepped: false,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 4,
      });
    default:
      return Object.assign({}, base, {
        backgroundColor: pale,
        borderWidth: 2,
        tension: 0.3,
        stepped: false,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 4,
      });
  }
}

function _graphVizPresetForKey(key) {
  const sid = GRAPH_VIZ_SELECT_IDS[key];
  const sel = sid ? document.getElementById(sid) : null;
  const v = sel && sel.value;
  return v && VALID_GRAPH_VIZ_PRESETS.has(v) ? v : DEFAULT_GRAPH_VIZ;
}

function _graphDisplayModeForKey(key) {
  const sid = GRAPH_DISPLAY_IDS[key];
  const sel = sid ? document.getElementById(sid) : null;
  const v = sel && sel.value;
  return v && VALID_DISPLAY_MODES.has(v) ? v : DEFAULT_DISPLAY_MODE;
}

/** Labels for CSV/export; timestamps stay on HIST.timestamps ISO sidecar. */
function _labelsAndDatasetsFromReadings(readings) {
  const labels = readings.map(r => {
    const d = new Date(r.timestamp);
    return isNaN(d.getTime()) ? '' : d.toLocaleString([], {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  });
  const datasets = {
    temp: readings.map(r => r.temperature),
    hum: readings.map(r => r.humidity),
    light: readings.map(r => r.light),
    height: readings.map(r => r.height),
  };
  return { labels, datasets };
}

function _histLengthsAligned() {
  const n = Array.isArray(HIST.timestamps) ? HIST.timestamps.length : 0;
  if (!n || !Array.isArray(HIST.labels) || HIST.labels.length !== n) return false;
  return ['temp', 'hum', 'light', 'height'].every(k => Array.isArray(HIST[k]) && HIST[k].length === n);
}

function _readingsReconstructedFromHist() {
  if (!_histLengthsAligned()) return null;
  const n = HIST.timestamps.length;
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push({
      timestamp: HIST.timestamps[i],
      temperature: HIST.temp[i],
      humidity: HIST.hum[i],
      light: HIST.light[i],
      height: HIST.height[i],
    });
  }
  return out;
}

/** Chart.js tooltip title when x is time ms */
function _tooltipTitleMillis(items) {
  const item = items && items[0];
  if (!item) return '';
  let x = item.parsed && item.parsed.x != null ? item.parsed.x : null;
  if (x == null && item.raw && typeof item.raw === 'object' && item.raw.x != null) x = item.raw.x;
  if (!Number.isFinite(Number(x))) return '';
  const dt = new Date(Number(x));
  return isNaN(dt.getTime())
    ? String(x)
    : dt.toLocaleString([], {
        weekday: 'short', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
}

function _linearTimeXScale() {
  return {
    type: 'linear',
    ticks: {
      font: { family: 'DM Mono', size: 9 },
      maxTicksLimit: 10,
      callback: function (value) {
        const dt = new Date(value);
        return isNaN(dt.getTime()) ? value : dt.toLocaleString([], {
          month: 'short', day: 'numeric',
          hour: '2-digit', minute: '2-digit',
        });
      },
    },
    grid: { display: false },
  };
}

function _updateDenseBarHint(maxPointsNeedingWarn) {
  const el = document.getElementById('graphDenseBarHint');
  if (!el) return;
  const n = maxPointsNeedingWarn || 0;
  if (n >= GRAPH_BAR_DENSITY_HINT_AFTER) {
    el.style.display = 'block';
    el.textContent = 'Dense bar view (\u2265' + GRAPH_BAR_DENSITY_HINT_AFTER +
      ' points): increase Bin (e.g. 5\u201310 min) for clearer hourly patterns.';
  } else {
    el.style.display = 'none';
    el.textContent = '';
  }
}

function refreshGraphHeatmap() {
  const wrap = document.getElementById('graphHeatmapWrap');
  const sel = document.getElementById('graphHeatmapMetric');
  const metricKey = (sel && sel.value) || 'temp';
  const field = READING_FIELD[metricKey];
  const meta = SENSOR_META[metricKey] || SENSOR_META.temp;
  if (!wrap || !field) return;

  const rows = lastChartReadings && lastChartReadings.length
    ? lastChartReadings
    : (_readingsReconstructedFromHist() || []);
  if (!rows.length) {
    wrap.innerHTML = '<div style="font-size:11px;color:var(--bark-mid);">No telemetry in memory for heatmap.</div>';
    return;
  }

  const buckets = {}; // key yyyy-mm-dd -> hour 0-23 -> { sum, n }
  let vmin = Infinity;
  let vmax = -Infinity;

  function dayKey(dt) {
    return dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0');
  }

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const ms = _parseTsMs(r.timestamp);
    if (!Number.isFinite(ms)) continue;
    const v = r[field];
    if (v == null || Number.isNaN(Number(v))) continue;
    const dt = new Date(ms);
    const dk = dayKey(dt);
    const h = dt.getHours();
    if (!buckets[dk]) buckets[dk] = {};
    if (!buckets[dk][h]) buckets[dk][h] = { sum: 0, n: 0 };
    buckets[dk][h].sum += Number(v);
    buckets[dk][h].n++;
  }

  const days = Object.keys(buckets).sort();
  days.forEach(dk => {
    for (let h = 0; h < 24; h++) {
      const cell = buckets[dk] && buckets[dk][h];
      if (!cell || !cell.n) continue;
      const avg = cell.sum / cell.n;
      if (avg < vmin) vmin = avg;
      if (avg > vmax) vmax = avg;
    }
  });

  if (!days.length || !Number.isFinite(vmin) || !Number.isFinite(vmax)) {
    wrap.innerHTML = '<div style="font-size:11px;color:var(--bark-mid);">No usable readings for heatmap.</div>';
    return;
  }
  const range = vmax - vmin;
  const norm = range > 1e-9 ? function (avg) {
    const t = (avg - vmin) / range;
    const g = Math.round(100 + t * 100);
    const b = Math.round(40 + (1 - t) * 80);
    return 'rgb(' + g + ',' + Math.round(60 + t * 40) + ',' + b + ')';
  } : function () { return '#e8e3d0'; };

  let html = '<div class="graph-heatmap-caption" style="font-size:10px;color:var(--bark-mid);margin:0 0 8px;">' +
    meta.label + ' · mean per cell (day \u00d7 hour, local time)</div>';
  html += '<div class="graph-heatmap-grid">';
  html += '<div class="graph-heatmap-corner"></div>';
  for (let h = 0; h < 24; h++)
    html += '<div class="graph-heatmap-hlabel">' + h + 'h</div>';

  days.forEach(dk => {
    html += '<div class="graph-heatmap-rowlabel">' + dk + '</div>';
    for (let h = 0; h < 24; h++) {
      const cell = buckets[dk] && buckets[dk][h];
      const avg = cell && cell.n ? cell.sum / cell.n : null;
      const bg = avg == null ? '#f5f3ec' : norm(avg);
      const tip = avg == null ? dk + ' ' + h + ':00 — no samples' :
        dk + ' ' + h + ':00 \u2192 mean ' + avg.toFixed(2) + meta.unit.trim();
      html += '<div class="graph-heatmap-cell" title="' + tip.replace(/"/g, '&quot;') + '" style="background:' + bg + ';"></div>';
    }
  });
  html += '</div>';

  wrap.innerHTML = html;
}

function _allCardsLineFamily() {
  return Object.keys(SENSOR_META).every(k => {
    const m = _graphDisplayModeForKey(k);
    return m === 'line' || m === 'area';
  });
}

/**
 * Cheap in-place preset refresh when linear x datasets already match aligned Y arrays (line/area only).
 */
function _tryApplyGraphVizPresetsOnly(timesMs, datasetsY) {
  if (typeof Chart === 'undefined' || !_allCardsLineFamily()) return false;
  const keys = Object.keys(SENSOR_META);
  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const ch = charts[key];
    if (!(ch && typeof ch.update === 'function' && ch.data && ch.data.datasets && ch.data.datasets[0])) return false;
    if (!ch.canvas || !ch.canvas.isConnected) return false;
    const display = _graphDisplayModeForKey(key);
    const pts = _zipXY(timesMs, datasetsY[key]);
    const wantMa = _movingAvgOverlayEnabled() && (display === 'line' || display === 'area') && pts.length >= 3;
    const hasMa = ch.data.datasets.length > 1 && String(ch.data.datasets[1].label || '').indexOf('Moving avg') !== -1;
    if (wantMa !== hasMa) return false;
    if (!pts.length) return false;
    const ds0 = ch.data.datasets[0];
    if (!ds0.data || ds0.data.length !== pts.length) return false;
  }
  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const meta = SENSOR_META[key];
    const preset = _graphVizPresetForKey(key);
    const display = _graphDisplayModeForKey(key);
    const style = _styleForRender(preset, meta.color, display, 'line');
    const ch = charts[key];
    const pts = _zipXY(timesMs, datasetsY[key]);
    ch.data.datasets[0].data = pts;
    Object.assign(ch.data.datasets[0], style);
    if (preset !== 'points') {
      delete ch.data.datasets[0].pointBackgroundColor;
      delete ch.data.datasets[0].pointBorderColor;
      delete ch.data.datasets[0].pointBorderWidth;
    }
    if (ch.data.datasets[1] && String(ch.data.datasets[1].label || '').indexOf('Moving avg') !== -1) {
      const maYs = _rollingMeanY(datasetsY[key], Math.max(1, Math.min(24, Math.floor(datasetsY[key].length / 80))));
      ch.data.datasets[1].data = _zipXY(timesMs, maYs);
    }
  }
  keys.forEach(key => { charts[key].update(); });
  return true;
}

/**
 * Resolved style fragment for Chart dataset (preset + forced area fill + bar defaults).
 */
function _styleForRender(preset, hexColor, displayMode, chartRootType) {
  const sty = Object.assign({}, _datasetStyleFromPreset(preset, hexColor));
  if (displayMode === 'area')
    sty.fill = true;

  if (chartRootType === 'bar') {
    return {
      borderColor: hexColor,
      backgroundColor: hexColor + '88',
      borderWidth: 1,
      borderRadius: 3,
      borderSkipped: false,
    };
  }
  if (chartRootType === 'scatter') {
    return Object.assign({}, sty, {
      fill: false,
      showLine: false,
      tension: 0,
      stepped: false,
      pointRadius: Math.max(sty.pointRadius || 4, 3),
      pointHoverRadius: sty.pointHoverRadius || 6,
    });
  }
  return sty;
}

function _buildDatasetsForKey(key, timesMs, yArr, meta) {
  const points = _zipXY(timesMs, yArr);
  const display = _graphDisplayModeForKey(key);
  const preset = _graphVizPresetForKey(key);

  let rootType = 'line';
  if (display === 'bar') rootType = 'bar';
  else if (display === 'scatter') rootType = 'scatter';

  let chartType = rootType === 'scatter' ? 'scatter' : (rootType === 'bar' ? 'bar' : 'line');

  const style = _styleForRender(preset, meta.color, display, rootType === 'scatter' ? 'scatter' : (rootType === 'bar' ? 'bar' : 'line'));

  const main = Object.assign({
    type: chartType,
    label: meta.label,
    data: points,
    order: 0,
    spanGaps: true,
  }, style);

  const out = [main];

  const wantMa = _movingAvgOverlayEnabled() && (display === 'line' || display === 'area');
  if (wantMa && points.length >= 3) {
    const hw = Math.max(1, Math.min(24, Math.floor(points.length / 80)));
    const maY = _rollingMeanY(yArr, hw);
    const maPts = _zipXY(timesMs, maY);
    if (maPts.length) {
      out.push({
        type: 'line',
        label: 'Moving avg',
        data: maPts,
        order: 5,
        borderColor: meta.color + 'aa',
        backgroundColor: 'transparent',
        borderWidth: 1.8,
        borderDash: [5, 4],
        tension: 0.35,
        fill: false,
        pointRadius: 0,
        spanGaps: true,
      });
    }
  }

  return { rootType, datasets: out, pointCount: points.length };
}

function _renderFourSensorCharts(labels, datasetsY) {
  const timesMs = _timesMsAlignedWithHist();
  const thresholds = _readThresholds();
  let maxBarPoints = 0;

  Object.keys(SENSOR_META).forEach(key => {
    const meta = SENSOR_META[key];
    const wrapId = 'chart' + key.charAt(0).toUpperCase() + key.slice(1) + 'Wrap';
    const wrap = document.getElementById(wrapId);
    if (!wrap) return;
    if (!wrap.querySelector('canvas')) {
      wrap.innerHTML = '<canvas id="chart_' + key + '" height="160"></canvas>';
    }
    const ctx = document.getElementById('chart_' + key);
    if (!ctx) return;
    if (charts[key]) charts[key].destroy();

    let annotation = null;
    let panelThr = thresholds[key];
    let panelDir = meta.warnDir;
    let panelMode = 'warn';

    if (key === 'height') {
      const gel = meta.goalId ? document.getElementById(meta.goalId) : null;
      const gv = gel ? parseFloat(gel.value) : NaN;
      panelThr = Number.isFinite(gv) ? gv : null;
      annotation = panelThr != null ? _buildGoalLineAnnotation(panelThr) : null;
      panelMode = panelThr != null ? 'goal' : 'warn';
      panelDir = 'high';
    } else {
      annotation = _buildAnnotation(thresholds[key], meta.warnDir);
    }

    const display = _graphDisplayModeForKey(key);
    if (display === 'bar') {
      const pc = _zipXY(timesMs, datasetsY[key]).length;
      if (pc > maxBarPoints) maxBarPoints = pc;
    }

    const built = _buildDatasetsForKey(key, timesMs, datasetsY[key], meta);
    const rootType = built.rootType;

    const interactionMode = display === 'scatter' ? 'nearest' : 'index';

    charts[key] = new Chart(ctx, {
      type: rootType === 'bar' ? 'bar' : (rootType === 'scatter' ? 'scatter' : 'line'),
      data: { datasets: built.datasets },
      options: {
        responsive: true,
        animation: { duration: 250 },
        interaction: { mode: interactionMode, intersect: false, axis: 'x' },
        plugins: {
          legend: { display: built.datasets.length > 1 },
          tooltip: {
            callbacks: {
              title: function (items) { return _tooltipTitleMillis(items); },
              label: function (item) {
                const yv = item.parsed && item.parsed.y != null ? item.parsed.y : item.raw && item.raw.y;
                return (item.dataset.label || meta.label) + ': ' +
                  (yv == null || Number.isNaN(Number(yv)) ? '--' : Number(yv).toFixed(2) + meta.unit);
              },
            },
          },
          annotation: annotation ? { annotations: { threshold: annotation } } : { annotations: {} },
          zoom: {
            pan:  { enabled: true, mode: 'x' },
            zoom: { wheel: { enabled: true }, pinch: { enabled: true }, drag: { enabled: false }, mode: 'x' },
            limits: { x: { minRange: ZOOM_X_MIN_MS } },
          },
        },
        scales: {
          x: _linearTimeXScale(),
          y: {
            ticks: { font: { family: 'DM Mono', size: 10 } },
            grid: { color: '#e8e3d0' },
          },
        },
      },
    });

    _renderStatsPanel(
      'stats_' + key,
      _computeStats(datasetsY[key]),
      meta.unit,
      panelThr,
      panelDir,
      panelMode,
    );
  });

  _updateDenseBarHint(maxBarPoints);
}

function updateCharts(readings) {
  if (!readings || !readings.length) {
    lastChartReadings = null;
    showChartsOffline();
    return;
  }

  lastChartReadings = readings;
  _ensureGraphControlsDelegatedListener();
  _syncGraphVizSelectsFromStorage();
  _syncGraphDisplaySelectsFromStorage();

  const { labels, datasets } = _labelsAndDatasetsFromReadings(readings);
  HIST.labels = labels;
  HIST.timestamps = readings.map(r => r.timestamp);
  Object.keys(datasets).forEach(k => { HIST[k] = datasets[k]; });

  _renderFourSensorCharts(labels, datasets);
  updateHomeChart();
  refreshGraphHeatmap();
}

function rerenderChartsFromCachedReadings() {
  let labels;
  let datasetsY;

  if (lastChartReadings && lastChartReadings.length) {
    const built = _labelsAndDatasetsFromReadings(lastChartReadings);
    labels = built.labels;
    datasetsY = built.datasets;
    HIST.labels = labels;
    HIST.timestamps = lastChartReadings.map(r => r.timestamp);
    Object.keys(datasetsY).forEach(k => { HIST[k] = datasetsY[k]; });
  } else if (_histLengthsAligned()) {
    if (!lastChartReadings || !lastChartReadings.length) {
      lastChartReadings = _readingsReconstructedFromHist();
    }
    labels = HIST.labels.slice();
    datasetsY = {
      temp: HIST.temp.slice(),
      hum: HIST.hum.slice(),
      light: HIST.light.slice(),
      height: HIST.height.slice(),
    };
  } else return;

  const timesMs = HIST.timestamps.map(ts => _parseTsMs(ts));
  if (_tryApplyGraphVizPresetsOnly(timesMs, datasetsY)) return;

  _renderFourSensorCharts(labels, datasetsY);
  updateHomeChart();
  refreshGraphHeatmap();
}

function onGraphVizPresetChange(sensorKey) {
  if (!GRAPH_VIZ_SELECT_IDS[sensorKey]) return;
  const sel = document.getElementById(GRAPH_VIZ_SELECT_IDS[sensorKey]);
  if (sel && VALID_GRAPH_VIZ_PRESETS.has(sel.value)) {
    try { sessionStorage.setItem(GRAPH_VIZ_STORAGE_PREFIX + sensorKey, sel.value); } catch (e) { /* ignore */ }
  }
  rerenderChartsFromCachedReadings();
}

function onGraphDisplayModeChange(sensorKey) {
  if (!GRAPH_DISPLAY_IDS[sensorKey]) return;
  const sel = document.getElementById(GRAPH_DISPLAY_IDS[sensorKey]);
  if (sel && VALID_DISPLAY_MODES.has(sel.value)) {
    try { sessionStorage.setItem(GRAPH_DISPLAY_STORAGE_PREFIX + sensorKey, sel.value); } catch (e) { /* ignore */ }
  }
  rerenderChartsFromCachedReadings();
}

function onGraphMovingAvgToggle() {
  rerenderChartsFromCachedReadings();
}

function resetAllZoom() {
  Object.keys(charts).forEach(k => {
    const c = charts[k];
    if (c && typeof c.resetZoom === 'function') c.resetZoom();
  });
}

function updateHomeChart() {
  const sensor = document.getElementById('homeChartSensor')?.value || 'temp';
  const wrap = document.getElementById('homeChartWrap');
  if (!wrap || !HIST.labels.length) return;

  if (!wrap.querySelector('canvas')) {
    wrap.innerHTML = '<canvas id="homeChart" height="180"></canvas>';
  }

  const meta = SENSOR_META[sensor] || SENSOR_META.temp;
  const timesMs = _timesMsAlignedWithHist();
  const ySeries = HIST[sensor] || [];
  const homePts = _zipXY(timesMs, ySeries);
  if (charts.home) charts.home.destroy();

  charts.home = new Chart(document.getElementById('homeChart'), {
    type: 'line',
    data: {
      datasets: [{
        label: meta.label,
        data: homePts,
        borderColor: meta.color,
        backgroundColor: meta.color + '22',
        borderWidth: 2,
        tension: 0.3,
        fill: true,
        pointRadius: 0,
        spanGaps: true,
      }],
    },
    options: {
      responsive: true,
      animation: { duration: 300 },
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: function (items) { return _tooltipTitleMillis(items); },
            label: function (item) {
              const yv = item.parsed && item.parsed.y != null ? item.parsed.y : item.raw && item.raw.y;
              return meta.label + ': ' + (yv == null ? '--' : Number(yv).toFixed(2) + meta.unit);
            },
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          ticks: {
            font: { family: 'DM Mono', size: 9 },
            maxTicksLimit: 6,
            callback: function (value) {
              const dt = new Date(value);
              return isNaN(dt.getTime()) ? value : dt.toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              });
            },
          },
          grid: { display: false },
        },
        y: { ticks: { font: { family: 'DM Mono', size: 10 } }, grid: { color: '#e8e3d0' } },
      },
    },
  });
}

function showChartsOffline() {
  lastChartReadings = null;
  Object.keys(SENSOR_META).forEach(k => {
    if (!charts[k]) return;
    try { charts[k].destroy(); } catch (e) { /* ignore */ }
    delete charts[k];
  });
  if (charts.home) {
    try { charts.home.destroy(); } catch (e) { /* ignore */ }
    delete charts.home;
  }
  ['chartTempWrap', 'chartHumWrap', 'chartLightWrap', 'chartHeightWrap', 'homeChartWrap'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="skel" style="height:160px;border-radius:8px;"></div>';
  });
  ['stats_temp', 'stats_hum', 'stats_light', 'stats_height'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div style="font-size:11px;color:var(--bark-mid);">No data in window.</div>';
  });
  _updateDenseBarHint(0);
  const hw = document.getElementById('graphHeatmapWrap');
  if (hw) hw.innerHTML = '<div style="font-size:11px;color:var(--bark-mid);">Load telemetry to see hourly pattern by day.</div>';
}

function _ensureGraphControlsDelegatedListener() {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  if (window.__terrametricGraphControlsDelegated) return;
  window.__terrametricGraphControlsDelegated = true;
  document.addEventListener(
    'change',
    function (ev) {
      const el = ev.target;
      if (!el || el.tagName !== 'SELECT') return;
      if (el.id === 'graphHeatmapMetric') {
        refreshGraphHeatmap();
        return;
      }
      const vizKey = GRAPH_VIZ_SELECT_ID_TO_KEY[el.id];
      if (vizKey) {
        onGraphVizPresetChange(vizKey);
        return;
      }
      const dispKey = GRAPH_DISPLAY_ID_TO_KEY[el.id];
      if (dispKey) {
        onGraphDisplayModeChange(dispKey);
        return;
      }
    },
    false,
  );
}

if (typeof window !== 'undefined') {
  window.onGraphVizPresetChange = onGraphVizPresetChange;
  window.onGraphDisplayModeChange = onGraphDisplayModeChange;
  window.onGraphMovingAvgToggle = onGraphMovingAvgToggle;
  window.rerenderChartsFromCachedReadings = rerenderChartsFromCachedReadings;
  window.refreshGraphHeatmap = refreshGraphHeatmap;
}

(function initGraphGraphControlsUi() {
  if (typeof document === 'undefined') return;
  const run = function () {
    _ensureGraphControlsDelegatedListener();
    _syncGraphVizSelectsFromStorage();
    _syncGraphDisplaySelectsFromStorage();
  };
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', run);
  else
    run();
})();
