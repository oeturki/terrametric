// ─────────────────────────────────────────────
//  charts.js — Researcher-grade telemetry charts
//
//  Responsibilities:
//    * Render the four primary sensor charts on the View Data → Graphs tab.
//    * Render the same data downsampled into the Home page mini-chart.
//    * Compute richer per-channel stats (min, max, mean, median, σ, n, last).
//    * Annotate charts from tolerance inputs plus an optional plant height goal line.
//    * Allow pan/zoom via chartjs-plugin-zoom (wheel, pinch, drag-rect).
//
//  Data shape consumed:
//    readings = [{timestamp, temperature, humidity, light, height}, ...]
// ─────────────────────────────────────────────

let charts = {};
const HIST = { temp: [], hum: [], light: [], height: [], labels: [], timestamps: [] };

// Register the zoom plugin once (it's a global on window when loaded via CDN).
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

// ── Pure stats helpers ─────────────────────────

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
// ── Main chart renderer ────────────────────────

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
  // Threshold band: shaded region above (warnDir=high) or below (warnDir=low) the threshold line.
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

function updateCharts(readings) {
  if (!readings || !readings.length) { showChartsOffline(); return; }

  const labels = readings.map(r => {
    const t = new Date(r.timestamp);
    return t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  });

  const datasets = {
    temp:   readings.map(r => r.temperature),
    hum:    readings.map(r => r.humidity),
    light:  readings.map(r => r.light),
    height: readings.map(r => r.height),
  };

  HIST.labels = labels;
  HIST.timestamps = readings.map(r => r.timestamp);
  Object.keys(datasets).forEach(k => HIST[k] = datasets[k]);

  const thresholds = _readThresholds();

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

    const chartConfig = {      type: 'line',
      data: {
        labels,
        datasets: [{
          label: meta.label,
          data: datasets[key],
          borderColor: meta.color,
          backgroundColor: meta.color + '22',
          borderWidth: 2, pointRadius: 0, pointHoverRadius: 4,
          tension: 0.3, fill: true, spanGaps: true,
        }]
      },
      options: {
        responsive: true,
        animation: { duration: 250 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (item) => meta.label + ': ' + (item.parsed.y == null ? '--' : item.parsed.y.toFixed(2) + meta.unit),
            },
          },
          annotation: annotation ? { annotations: { threshold: annotation } } : { annotations: {} },
          zoom: {
            pan:  { enabled: true, mode: 'x' },
            zoom: { wheel: { enabled: true }, pinch: { enabled: true }, drag: { enabled: false }, mode: 'x' },
            limits: { x: { minRange: 5 } },
          },
        },
        scales: {
          x: { ticks: { font: { family: 'DM Mono', size: 9 }, maxTicksLimit: 8 }, grid: { display: false } },
          y: { ticks: { font: { family: 'DM Mono', size: 10 } }, grid: { color: '#e8e3d0' } },
        },
      },
    };
    charts[key] = new Chart(ctx, chartConfig);

    _renderStatsPanel(
      'stats_' + key,
      _computeStats(datasets[key]),
      meta.unit,
      panelThr,
      panelDir,
      panelMode,
    );
  });

  updateHomeChart();
}

// Reset zoom on every chart (called by the toolbar button).
function resetAllZoom() {
  Object.keys(charts).forEach(k => {
    const c = charts[k];
    if (c && typeof c.resetZoom === 'function') c.resetZoom();
  });
}

// ── Home page chart ──────────────────────────

function updateHomeChart() {
  const sensor = document.getElementById('homeChartSensor')?.value || 'temp';
  const wrap = document.getElementById('homeChartWrap');
  if (!wrap || !HIST.labels.length) return;

  if (!wrap.querySelector('canvas')) {
    wrap.innerHTML = '<canvas id="homeChart" height="180"></canvas>';
  }

  const meta = SENSOR_META[sensor] || SENSOR_META.temp;
  if (charts.home) charts.home.destroy();

  charts.home = new Chart(document.getElementById('homeChart'), {
    type: 'line',
    data: {
      labels: HIST.labels,
      datasets: [{
        label: meta.label,
        data: HIST[sensor] || [],
        borderColor: meta.color,
        backgroundColor: meta.color + '22',
        borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true,
      }]
    },
    options: {
      responsive: true, animation: { duration: 300 },
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font: { family: 'DM Mono', size: 9 }, maxTicksLimit: 6 }, grid: { display: false } },
        y: { ticks: { font: { family: 'DM Mono', size: 10 } }, grid: { color: '#e8e3d0' } }
      }
    }
  });
}

// ── Skeleton while waiting for data ─────────

function showChartsOffline() {
  ['chartTempWrap', 'chartHumWrap', 'chartLightWrap', 'chartHeightWrap', 'homeChartWrap'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="skel" style="height:160px;border-radius:8px;"></div>';
  });
  ['stats_temp', 'stats_hum', 'stats_light', 'stats_height'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div style="font-size:11px;color:var(--bark-mid);">No data in window.</div>';
  });
}
