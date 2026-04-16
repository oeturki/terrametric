// ─────────────────────────────────────────────
//  charts.js — All graph and chart logic
//  Uses Chart.js to draw live sensor graphs.
// ─────────────────────────────────────────────

let charts = {};
const HIST = { temp: [], hum: [], light: [], height: [], labels: [] };

// ── Update all 4 sensor charts ───────────────

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

  // Store history for home chart
  HIST.labels = labels;
  Object.keys(datasets).forEach(k => HIST[k] = datasets[k]);

  const thresholds = {
    temp:   parseFloat(document.getElementById('warn-temp')?.value)   || 28,
    hum:    parseFloat(document.getElementById('warn-hum')?.value)    || 80,
    light:  parseFloat(document.getElementById('warn-light')?.value)  || 200,
    height: parseFloat(document.getElementById('warn-height')?.value) || 35,
  };

  const colors = { temp: '#7a8c1e', hum: '#4a7c8f', light: '#c4711a', height: '#3d5016' };
  const units  = { temp: '°C',      hum: '%',       light: ' lux',    height: ' cm'    };

  const chartPairs = [
    ['temp',   'chartTempWrap'],
    ['hum',    'chartHumWrap'],
    ['light',  'chartLightWrap'],
    ['height', 'chartHeightWrap'],
  ];

  chartPairs.forEach(([key, wrapId]) => {
    const wrap = document.getElementById(wrapId);
    if (!wrap) return;

    // Replace skeleton with canvas on first data
    if (!wrap.querySelector('canvas')) {
      wrap.innerHTML = `<canvas id="chart_${key}" height="150"></canvas>`;
    }

    const ctx = document.getElementById('chart_' + key);
    if (!ctx) return;
    if (charts[key]) charts[key].destroy();

    charts[key] = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: key,
            data: datasets[key],
            borderColor: colors[key],
            backgroundColor: colors[key] + '22',
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.4,
            fill: true,
          },
          {
            label: 'Threshold',
            data: new Array(labels.length).fill(thresholds[key]),
            borderColor: '#e0a030',
            borderWidth: 1.5,
            borderDash: [5, 4],
            pointRadius: 0,
            fill: false,
          }
        ]
      },
      options: {
        responsive: true,
        animation: { duration: 400 },
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { font: { family: 'DM Mono', size: 9 }, maxTicksLimit: 6 }, grid: { display: false } },
          y: { ticks: { font: { family: 'DM Mono', size: 10 } }, grid: { color: '#e8e3d0' } }
        }
      }
    });

    // Update mini stat strip below each chart
    const arr = datasets[key].filter(v => v != null);
    if (arr.length) {
      setText(key + 'Min', Math.min(...arr).toFixed(1) + units[key]);
      setText(key + 'Max', Math.max(...arr).toFixed(1) + units[key]);
      setText(key + 'Avg', (arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(1) + units[key]);
    }
  });

  updateHomeChart();
}

// ── Home page telemetry chart ────────────────

function updateHomeChart() {
  const sensor = document.getElementById('homeChartSensor')?.value || 'temp';
  const wrap = document.getElementById('homeChartWrap');
  if (!wrap || !HIST.labels.length) return;

  if (!wrap.querySelector('canvas')) {
    wrap.innerHTML = '<canvas id="homeChart" height="180"></canvas>';
  }

  const colors = { temp: '#7a8c1e', hum: '#4a7c8f', light: '#c4711a' };
  if (charts.home) charts.home.destroy();

  charts.home = new Chart(document.getElementById('homeChart'), {
    type: 'line',
    data: {
      labels: HIST.labels,
      datasets: [{
        label: sensor,
        data: HIST[sensor] || [],
        borderColor: colors[sensor],
        backgroundColor: colors[sensor] + '22',
        borderWidth: 2,
        pointRadius: 2,
        tension: 0.4,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      animation: { duration: 300 },
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font: { family: 'DM Mono', size: 9 }, maxTicksLimit: 6 }, grid: { display: false } },
        y: { ticks: { font: { family: 'DM Mono', size: 10 } }, grid: { color: '#e8e3d0' } }
      }
    }
  });
}

// ── Skeleton fallback while waiting for data ─

function showChartsOffline() {
  ['chartTempWrap', 'chartHumWrap', 'chartLightWrap', 'chartHeightWrap', 'homeChartWrap'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="skel" style="height:160px;border-radius:8px;"></div>';
  });
}
