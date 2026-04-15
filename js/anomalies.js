// ─────────────────────────────────────────────
//  anomalies.js — Anomaly detection & simulation
//  Written by Omer (anomaly detection team).
//  Connects to /api/anomalies/simulate on the
//  backend to run drift/noise/dropout scenarios.
// ─────────────────────────────────────────────

let anomalyLog       = [];
let anomSimReadings  = [];
let anomSimActiveSensors = new Set(['temperature']);

// ── Fetch real anomalies from server ─────────

async function fetchAnomalies() {
  try {
    const d = await apiFetch(CONFIG.ENDPOINTS.anomalies);
    anomalyLog = d.events || d || [];
    setText('anomTotal',   d.total   ?? anomalyLog.length);
    setText('anomSpikes',  d.spikes  ?? anomalyLog.filter(a => a.type === 'noise').length);
    setText('anomMissing', d.missing ?? anomalyLog.filter(a => a.type === 'dropout').length);
    setText('anomDrift',   d.drift   ?? anomalyLog.filter(a => a.type === 'drift').length);
    renderAnomalyTable();
  } catch {
    setText('anomTotal',  '--');
    setText('anomSpikes', '--');
    setText('anomMissing','--');
    setText('anomDrift',  '--');
  }
}

// ── Run a simulation scenario ────────────────
// Calls POST /api/anomalies/simulate on the backend
// Scenarios: 'stable' | 'drift' | 'noise' | 'dropout' | 'all'

async function runAnomalySimulation() {
  const btn      = document.getElementById('simRunBtn');
  const card     = document.getElementById('anomChartCard');
  const scenario = document.getElementById('simScenario').value;
  const duration = document.getElementById('simDuration').value;

  // Show spinner
  btn.disabled = true;
  btn.textContent = 'Running…';
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:absolute;inset:0;background:rgba(245,242,232,.7);display:flex;align-items:center;justify-content:center;border-radius:12px;z-index:2;';
  overlay.innerHTML = '<div style="width:28px;height:28px;border:3px solid var(--cream-dark);border-top-color:var(--olive);border-radius:50%;animation:spin .6s linear infinite;"></div>';
  card.style.position = 'relative';
  card.appendChild(overlay);

  try {
    const res = await fetch(
      API_BASE + '/api/anomalies/simulate?scenario=' + scenario + '&duration_min=' + duration,
      { method: 'POST' }
    );
    const d = await res.json();

    anomSimReadings = d.readings || [];
    anomalyLog      = d.events   || [];

    setText('anomTotal',   d.total   ?? 0);
    setText('anomSpikes',  d.spikes  ?? 0);
    setText('anomMissing', d.missing ?? 0);
    setText('anomDrift',   d.drift   ?? 0);

    buildAnomSensorPills();
    renderAnomChart();
    renderAnomalyTable();

    const total = d.total || 0;
    fireAlert(
      total > 0 ? 'warning' : 'ok',
      'Simulation Complete',
      anomSimReadings.length + ' readings · ' + total + ' anomalies detected',
      5000
    );
  } catch (err) {
    fireAlert('danger', 'Simulation Failed', 'Make sure the server is running on port ' + CONFIG.PORT, 6000);
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Run';
    overlay.remove();
  }
}

// ── Clear simulation results ─────────────────

function clearAnomalySimulation() {
  fetch(API_BASE + '/api/anomalies/clear', { method: 'DELETE' }).catch(() => {});

  anomalyLog      = [];
  anomSimReadings = [];

  setText('anomTotal', '--');
  setText('anomSpikes', '--');
  setText('anomMissing', '--');
  setText('anomDrift', '--');

  if (charts.anomSim) { charts.anomSim.destroy(); charts.anomSim = null; }

  document.getElementById('anomChartWrap').innerHTML = `
    <div style="padding:32px;text-align:center;font-size:11px;color:var(--bark-mid);">
      <div style="font-size:28px;margin-bottom:8px;">📡</div>
      Select a scenario above and hit <strong>▶ Run</strong> to visualise simulated data
    </div>`;
  document.getElementById('anomSensorPills').innerHTML = '';
  document.getElementById('anomalyBody').innerHTML = `
    <div style="padding:32px;text-align:center;font-size:11px;color:var(--bark-mid);">
      <div style="font-size:28px;margin-bottom:8px;">📡</div>
      No anomalies detected yet — run a simulation or connect your system
    </div>`;
  document.getElementById('anomLogCount').textContent = '';
}

// ── Sensor toggle pills on the chart ─────────

function buildAnomSensorPills() {
  const container = document.getElementById('anomSensorPills');
  const available = new Set();
  for (const r of anomSimReadings) {
    for (const k of ['temperature', 'humidity', 'light', 'height']) {
      if (r[k] != null) available.add(k);
    }
  }
  container.innerHTML = '';
  for (const s of available) {
    const pill = document.createElement('button');
    pill.className = 'plant-tab' + (anomSimActiveSensors.has(s) ? ' active' : '');
    pill.textContent = s.charAt(0).toUpperCase() + s.slice(1);
    pill.onclick = () => {
      anomSimActiveSensors.has(s) ? anomSimActiveSensors.delete(s) : anomSimActiveSensors.add(s);
      pill.classList.toggle('active');
      renderAnomChart();
    };
    container.appendChild(pill);
  }
}

// ── Render simulation chart ───────────────────

function renderAnomChart() {
  const wrap = document.getElementById('anomChartWrap');
  if (!anomSimReadings.length) return;
  if (!wrap.querySelector('canvas')) {
    wrap.innerHTML = '<canvas id="anomSimChart" height="200"></canvas>';
  }
  if (charts.anomSim) charts.anomSim.destroy();

  const chartColors = { temperature: '#7a8c1e', humidity: '#4a7c8f', light: '#c4711a', height: '#3d5016' };
  const anomStyles  = {
    drift:   { color: '#4a7c8f', point: 'triangle' },
    noise:   { color: '#a83232', point: 'circle'   },
    dropout: { color: '#c4711a', point: 'rectRot'  },
  };

  const labels   = anomSimReadings.map(r => new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  const datasets = [];

  // One line per active sensor
  for (const sensor of anomSimActiveSensors) {
    datasets.push({
      label: sensor.charAt(0).toUpperCase() + sensor.slice(1),
      data: anomSimReadings.map(r => r[sensor]),
      borderColor: chartColors[sensor] || '#7a8c1e',
      backgroundColor: (chartColors[sensor] || '#7a8c1e') + '22',
      borderWidth: 2, pointRadius: 1.5, tension: 0.4, fill: true,
    });
  }

  // Overlay anomaly event markers
  const rMap = {};
  anomSimReadings.forEach(r => rMap[r.timestamp] = r);
  const firstSensor = [...anomSimActiveSensors][0] || 'temperature';

  for (const [type, style] of Object.entries(anomStyles)) {
    const typeEvts = anomalyLog.filter(e => e.type === type);
    if (!typeEvts.length) continue;
    datasets.push({
      label: type.charAt(0).toUpperCase() + type.slice(1) + ' anomaly',
      data: typeEvts
        .map(e => ({ x: labels[anomSimReadings.findIndex(r => r.timestamp === e.timestamp)] || '', y: rMap[e.timestamp]?.[firstSensor] ?? null }))
        .filter(d => d.y !== null),
      pointStyle: style.point, pointRadius: 7,
      pointBorderColor: style.color, pointBackgroundColor: style.color + '66', pointBorderWidth: 2,
      showLine: false,
    });
  }

  charts.anomSim = new Chart(document.getElementById('anomSimChart'), {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, animation: { duration: 400 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { font: { family: 'DM Mono', size: 10 }, usePointStyle: true, padding: 14 } },
        tooltip: { backgroundColor: '#2c2a1e', titleFont: { family: 'Syne', weight: '700' }, bodyFont: { family: 'DM Mono', size: 11 }, cornerRadius: 8, padding: 10 }
      },
      scales: {
        x: { ticks: { font: { family: 'DM Mono', size: 9 }, maxTicksLimit: 12 }, grid: { display: false } },
        y: { ticks: { font: { family: 'DM Mono', size: 10 } }, grid: { color: '#e8e3d0' } }
      }
    }
  });
}

// ── Render anomaly event table ────────────────

function renderAnomalyTable() {
  const typeF   = document.getElementById('anomFilterType')?.value   || '';
  const sevF    = document.getElementById('anomFilterSev')?.value    || '';
  const sensorF = document.getElementById('anomFilterSensor')?.value || '';

  let filtered = anomalyLog;
  if (typeF)   filtered = filtered.filter(e => e.type   === typeF);
  if (sevF)    filtered = filtered.filter(e => e.severity === sevF);
  if (sensorF) filtered = filtered.filter(e => e.sensor  === sensorF);

  const countEl = document.getElementById('anomLogCount');
  if (countEl) countEl.textContent = filtered.length ? '(' + filtered.length + ')' : '';

  const body = document.getElementById('anomalyBody');
  if (!body) return;

  if (!filtered.length) {
    body.innerHTML = '<div style="padding:32px;text-align:center;font-size:11px;color:var(--bark-mid)"><div style="font-size:28px;margin-bottom:8px">✅</div>No matching anomalies</div>';
    return;
  }

  body.innerHTML = filtered.slice(0, 50).map(a => {
    const typeClass = a.type === 'drift' ? 'info' : a.type === 'noise' ? 'danger' : 'warning';
    return `
      <div class="tbl-row" style="grid-template-columns:140px 80px 100px 1fr 90px 80px;">
        <span style="font-size:10px;">${new Date(a.timestamp).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
        <span><span class="sev-pill ${typeClass}" style="text-transform:uppercase;">${a.type || '—'}</span></span>
        <span>${a.sensor || '—'}</span>
        <span style="font-size:10px;">${a.description}</span>
        <span><span class="sev-pill ${a.severity}">${(a.severity || '').toUpperCase()}</span></span>
        <span><span class="status-pill ${a.status === 'resolved' ? 'resolved' : 'active'}">${a.status === 'resolved' ? 'Resolved' : 'Active'}</span></span>
      </div>`;
  }).join('');
}

// ── Export anomaly log as CSV ─────────────────

function exportAnomalyCSV() {
  if (!anomalyLog.length) { fireAlert('warning', 'No Data', 'Run a simulation first.', 3000); return; }
  const rows = [
    'Timestamp,Type,Sensor,Description,Severity,Status',
    ...anomalyLog.map(e => `"${e.timestamp}","${e.type}","${e.sensor}","${e.description}","${e.severity}","${e.status || 'active'}"`)
  ];
  downloadFile('terrametric-anomalies.csv', rows.join('\n'), 'text/csv');
}
