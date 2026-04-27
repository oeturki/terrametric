// ─────────────────────────────────────────────
//  anomalies.js — Anomaly detection & simulation
//  Loaded by frontend/index.html (View Data → Anomalies tab).
// ─────────────────────────────────────────────

let anomalyLog = [];

const ANOM_PAGE_SIZE = 45;
let anomLogVisible = ANOM_PAGE_SIZE;
let anomAckKeys = new Set();
let anomFocusTs = null;

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

let anomSimReadings = [];
let anomSimActiveSensors = new Set(['temperature']);

async function fetchAnomalies() {
  try {
    const d = await apiFetch(CONFIG.ENDPOINTS.anomalies);
    anomalyLog = d.events || d || [];
    updateAnomalySummaryCards(d);
    renderAnomalyTable();
  } catch {
    resetAnomalySummaryCards();
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
};
const SCENARIO_INFO = {
  stable:      'Generates clean data at setpoints with normal sensor noise. Should produce zero anomalies — use as a baseline sanity check.',
  drift:       'Applies a linear temperature increase of 0.15°C per reading, simulating a heater malfunction or calibration drift.',
  noise:       'Injects high-variance Gaussian noise (σ=4.0) onto temperature in the second half, simulating electrical interference or a failing sensor.',
  dropout:     'Removes 8 consecutive readings mid-stream, simulating a Bluetooth disconnection or sensor power loss.',
  spike:       'Inserts 3 extreme outlier readings (±15°C from normal), simulating DHT11 glitch values of 0 or 255.',
  level_shift: 'Applies an abrupt +8°C step change halfway through — like someone opening a greenhouse door and leaving it open.',
  correlation: 'Randomises humidity independently of temperature for 30% of the data, breaking the physical correlation the DHT11 normally produces.',
  all:         'Applies every injection simultaneously: drift + noise + dropout + spikes + level shift + correlation break. Stress-test for the full detection pipeline.',
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

function formatScenarioLabel(scenario) {
  if (!scenario) return '';
  return scenario.split('_').map(function(part) {
    return part ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : '';
  }).join(' ');
}

async function runAnomalySimulation() {
  const btn = document.getElementById('simRunBtn');
  const card = document.getElementById('anomChartCard');
  btn.disabled = true; btn.textContent = 'Running…';
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:absolute;inset:0;background:rgba(245,242,232,.7);display:flex;align-items:center;justify-content:center;border-radius:12px;z-index:2;';
  overlay.innerHTML = '<div style="width:28px;height:28px;border:3px solid var(--cream-dark);border-top-color:var(--olive);border-radius:50%;animation:spin .6s linear infinite;"></div>';
  card.style.position = 'relative';
  card.appendChild(overlay);

  const scenario = document.getElementById('simScenario').value;
  const duration = document.getElementById('simDuration').value;

  const infoPanel = document.getElementById('anomScenarioInfo');
  const tagEl = document.getElementById('anomScenarioTag');
  const descEl = document.getElementById('anomScenarioDesc');
  if (infoPanel && tagEl && descEl) {
    infoPanel.classList.add('is-visible');
    tagEl.textContent = formatScenarioLabel(scenario);
    descEl.textContent = SCENARIO_INFO[scenario] || '';
  }

  try {
    const res = await authFetch(API_BASE + '/api/anomalies/simulate?scenario=' + scenario + '&duration_min=' + duration, { method: 'POST' });
    const d = await res.json();
    anomSimReadings = d.readings || [];
    anomalyLog = d.events || [];
    updateAnomalySummaryCards(d);
    buildAnomSensorPills();
    anomResetVisible();
    renderAnomCharts();
    renderAnomalyScoreTimeline();
    renderAnomalyTable();
    const total = d.total || 0;
    fireAlert(total > 0 ? 'warning' : 'ok', 'Simulation Complete', anomSimReadings.length + ' readings · ' + total + ' anomalies detected', 5000);
  } catch (err) {
    fireAlert('danger', 'Simulation Failed', 'Cannot reach backend — make sure uvicorn is running on port ' + CONFIG.PORT, 6000);
    console.error(err);
  } finally {
    btn.disabled = false; btn.textContent = 'Run simulation';
    overlay.remove();
  }
}

function clearAnomalySimulation() {
  authFetch(API_BASE + '/api/anomalies/clear', { method: 'DELETE' }).catch(() => {});
  anomalyLog = []; anomSimReadings = [];
  anomResetVisible();
  anomFocusTs = null;
  document.getElementById('anomFocusBar')?.classList.remove('visible');
  resetAnomalySummaryCards();
  if (charts.anomSim) { for (const c of Object.values(charts.anomSim)) { if (c && c.destroy) c.destroy(); } charts.anomSim = null; }
  if (charts.anomScore) { charts.anomScore.destroy(); charts.anomScore = null; }
  document.getElementById('anomChartWrap').innerHTML = '<div class="anom-placeholder"><span class="anom-placeholder__glyph" aria-hidden="true">◇</span><p class="anom-placeholder__text">Configure a scenario and choose <strong>Run simulation</strong> to generate synthetic telemetry and detector output.</p></div>';
  document.getElementById('anomScoreWrap').innerHTML = '<div class="anom-placeholder anom-placeholder--compact"><p class="anom-placeholder__text">Scores appear after a successful simulation run.</p></div>';
  document.getElementById('anomSensorPills').innerHTML = '';
  document.getElementById('anomalyBody').innerHTML = '<div class="anom-placeholder"><span class="anom-placeholder__glyph" aria-hidden="true">◇</span><p class="anom-placeholder__text">No events loaded. Run a simulation or connect live telemetry to populate this register.</p></div>';
  document.getElementById('anomLogCount').textContent = '';
  const infoPanel = document.getElementById('anomScenarioInfo');
  if (infoPanel) infoPanel.classList.remove('is-visible');
}

function buildAnomSensorPills() {
  const container = document.getElementById('anomSensorPills');
  const available = new Set();
  for (const r of anomSimReadings) {
    for (const k of ['temperature','humidity','light','height']) { if (r[k] != null) available.add(k); }
  }
  container.innerHTML = '';
  for (const s of available) {
    const pill = document.createElement('button');
    pill.className = 'plant-tab' + (anomSimActiveSensors.has(s) ? ' active' : '');
    pill.textContent = s.charAt(0).toUpperCase() + s.slice(1);
    pill.onclick = () => { anomSimActiveSensors.has(s) ? anomSimActiveSensors.delete(s) : anomSimActiveSensors.add(s); pill.classList.toggle('active'); renderAnomCharts(); };
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

  const labels = anomSimReadings.map(r => { const t = new Date(r.timestamp); return t.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}); });
  const rMap = {}; anomSimReadings.forEach(r => rMap[r.timestamp] = r);

  let html = '';
  for (const sensor of activeSensors) {
    html += '<div style="margin-bottom:6px;"><canvas id="anomChart_' + sensor + '" height="' + (activeSensors.length > 1 ? 100 : 180) + '"></canvas></div>';
  }
  wrap.innerHTML = html;

  for (const sensor of activeSensors) {
    const datasets = [{
      label: sensor.charAt(0).toUpperCase() + sensor.slice(1) + ' (' + (ANOM_UNITS[sensor]||'') + ')',
      data: anomSimReadings.map(r => r[sensor]),
      borderColor: ANOM_COLORS[sensor], backgroundColor: ANOM_COLORS[sensor] + '18',
      borderWidth: 1.5, pointRadius: 0.8, tension: 0.3, fill: true, order: 2,
    }];

    if (showMarkers) {
      const sensorEvents = anomalyLog.filter(e => e.sensor === sensor || (sensor === 'temperature' && e.sensor === 'temperature+humidity'));
      const byType = {};
      for (const e of sensorEvents) { (byType[e.type] = byType[e.type] || []).push(e); }
      for (const [type, evts] of Object.entries(byType)) {
        const meta = ANOM_TYPE_META[type] || { color:'#999', label:type };
        datasets.push({
          label: meta.label,
          data: evts.map(e => {
            const idx = anomSimReadings.findIndex(r => r.timestamp === e.timestamp);
            return idx >= 0 ? { x: labels[idx], y: rMap[e.timestamp]?.[sensor] ?? null } : null;
          }).filter(Boolean),
          pointStyle: 'triangle',
          pointRadius: 6, pointBorderColor: meta.color, pointBackgroundColor: meta.color + '88',
          pointBorderWidth: 2, showLine: false, order: 1,
        });
      }
    }

    charts.anomSim[sensor] = new Chart(document.getElementById('anomChart_' + sensor), {
      type: 'line', data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: true, animation: { duration: 300 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { font: { family:'DM Mono', size:9 }, usePointStyle: true, padding:10 } },
          tooltip: { backgroundColor:'#2c2a1e', titleFont:{ family:'Syne', weight:'700' }, bodyFont:{ family:'DM Mono', size:10 }, cornerRadius:8, padding:8,
            callbacks: { afterBody: function(ctx) {
              const idx = ctx[0]?.dataIndex;
              if (idx == null) return '';
              const ts = anomSimReadings[idx]?.timestamp;
              const evts = anomalyLog.filter(e => e.timestamp === ts && (e.sensor === sensor || e.sensor === 'temperature+humidity'));
              if (!evts.length) return '';
              return '\n--- Anomalies ---\n' + evts.map(e => (ANOM_TYPE_META[e.type]?.icon||'') + ' ' + e.type + ': ' + (e.description||'').slice(0,60)).join('\n');
            }}
          }
        },
        scales: {
          x: { ticks:{ font:{ family:'DM Mono', size:8 }, maxTicksLimit:10 }, grid:{ display:false } },
          y: { title:{ display:true, text:sensor.charAt(0).toUpperCase()+sensor.slice(1)+' ('+( ANOM_UNITS[sensor]||'')+')', font:{ family:'Syne', size:10, weight:'700' } }, ticks:{ font:{ family:'DM Mono', size:9 } }, grid:{ color:'#e8e3d0' } }
        }
      }
    });
  }
}

function renderAnomalyScoreTimeline() {
  const wrap = document.getElementById('anomScoreWrap');
  if (!anomSimReadings.length || !anomalyLog.length) { wrap.innerHTML = '<div class="anom-placeholder anom-placeholder--compact"><p class="anom-placeholder__text">No scored anomalies for this run.</p></div>'; return; }

  if (charts.anomScore) charts.anomScore.destroy();
  wrap.innerHTML = '<canvas id="anomScoreChart" height="80"></canvas>';

  const labels = anomSimReadings.map(r => new Date(r.timestamp).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}));
  const scores = anomSimReadings.map(r => {
    const evts = anomalyLog.filter(e => e.timestamp === r.timestamp);
    let score = 0;
    for (const e of evts) { score += e.severity === 'danger' ? 3 : e.severity === 'warning' ? 2 : 1; }
    return score;
  });

  const gradient = document.getElementById('anomScoreChart').getContext('2d');
  const g = gradient.createLinearGradient(0,0,0,80);
  g.addColorStop(0,'rgba(168,50,50,0.6)'); g.addColorStop(1,'rgba(168,50,50,0.02)');

  charts.anomScore = new Chart(document.getElementById('anomScoreChart'), {
    type: 'bar', data: { labels, datasets: [{ label:'Anomaly Score', data:scores, backgroundColor:g, borderColor:'rgba(168,50,50,0.7)', borderWidth:1, borderRadius:2 }] },
    options: {
      responsive:true, maintainAspectRatio:true, animation:{duration:300},
      plugins:{ legend:{display:false}, tooltip:{ backgroundColor:'#2c2a1e', bodyFont:{family:'DM Mono',size:10}, cornerRadius:6, callbacks:{ label:ctx => 'Score: '+ctx.raw+' ('+anomalyLog.filter(e=>e.timestamp===anomSimReadings[ctx.dataIndex]?.timestamp).length+' events)' } } },
      scales:{ x:{display:false}, y:{beginAtZero:true,ticks:{font:{family:'DM Mono',size:9},stepSize:1},grid:{color:'#e8e3d033'}} }
    }
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
    body.innerHTML = '<div class="anom-placeholder"><span class="anom-placeholder__glyph" aria-hidden="true">◇</span><p class="anom-placeholder__text">No events match the current filters.</p></div>';
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
  if (!anomalyLog.length) { fireAlert('warning','No Data','Run a simulation first.',3000); return; }
  const header = 'Timestamp,Type,Sensor,Description,Severity,Status';
  const rows = anomalyLog.map(e => {
    const desc = (e.description == null ? '' : String(e.description)).replace(/"/g,'""');
    return `"${e.timestamp}","${e.type}","${e.sensor}","${desc}","${e.severity}","${e.status||'active'}"`;
  });
  downloadFile('terrametric-anomalies.csv', [header, ...rows].join('\n'), 'text/csv');
}

function printAnomalyReport() {
  if (!anomalyLog.length) { fireAlert('warning','No Data','Run a simulation first.',3000); return; }
  const w = window.open('', '_blank');
  const scenario = document.getElementById('simScenario').value;
  let html = '<html><head><title>TerraMetric Anomaly Report</title><style>body{font-family:Arial,sans-serif;padding:40px;color:#333;}h1{font-size:18px;}table{border-collapse:collapse;width:100%;margin-top:16px;font-size:11px;}th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;}th{background:#f5f0e0;}.badge{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:bold;}.danger{background:#ffe0e0;color:#8a1010;}.warning{background:#fff0c0;color:#8a5000;}.info{background:#e0f0ff;color:#204060;}</style></head><body>';
  html += '<h1>TerraMetric Anomaly Detection Report</h1>';
  html += '<p style="font-size:12px;color:#666;">Scenario: <strong>' + escapeHtml(scenario) + '</strong> · Generated: ' + new Date().toLocaleString() + ' · Total events: ' + anomalyLog.length + '</p>';
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
