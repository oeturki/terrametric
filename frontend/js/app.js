// ─────────────────────────────────────────────
//  app.js — Navigation, connection check,
//           utility helpers, and boot sequence
// ─────────────────────────────────────────────

(function requireLoginShell() {
  try {
    if (!document.getElementById('page-home')) return;
    if (typeof getAccessToken === 'function' && !getAccessToken()) {
      window.location.replace('login.html');
    }
  } catch (_) { /* non-browser */ }
})();

let isConnected = false;

// ── Page navigation ──────────────────────────
// index.html holds all sections. Standalone *.html files only contain one section — goTo would fail.
// If the target section is missing, send the user to the SPA shell on index.html.

function _afterPageShow(page) {
  if (page === 'samples') {
    buildTrayList();
    if (typeof loadDevicesForSamples === 'function') loadDevicesForSamples();
    if (typeof refreshActiveRecording === 'function') refreshActiveRecording();
  }
  if (page === 'viewdata') buildGalleryTabs();
  if (page === 'control' && typeof fetchControls === 'function') {
    fetchControls();
  }
}

function goTo(page, navEl) {
  const target = document.getElementById('page-' + page);
  if (!target) {
    window.location.assign(new URL('index.html#' + page, window.location.href).href);
    return;
  }
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  target.classList.add('active');
  if (navEl) navEl.classList.add('active');
  try {
    if (document.getElementById('page-home')) {
      history.replaceState(null, '', '#' + page);
    }
  } catch (e) { /* file:// or restricted */ }
  _afterPageShow(page);
}

/** When using index.html as SPA: sync sidebar to URL hash (e.g. bookmark index.html#samples). */
function applyRouteFromHash() {
  if (!document.getElementById('page-home')) return;
  const raw = (location.hash || '#home').replace(/^#/, '').trim();
  const valid = ['home', 'viewdata', 'control', 'samples'];
  const page = valid.includes(raw) ? raw : 'home';
  const navItems = document.querySelectorAll('.nav-item');
  const map = { home: 0, viewdata: 1, control: 2, samples: 3 };
  const idx = map[page];
  if (navItems[idx]) goTo(page, navItems[idx]);
}

window.addEventListener('hashchange', function () {
  if (!document.getElementById('page-home')) return;
  const raw = (location.hash || '#home').replace(/^#/, '').trim();
  const valid = ['home', 'viewdata', 'control', 'samples'];
  if (!valid.includes(raw)) return;
  const target = document.getElementById('page-' + raw);
  if (!target) return;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  target.classList.add('active');
  const navItems = document.querySelectorAll('.nav-item');
  const map = { home: 0, viewdata: 1, control: 2, samples: 3 };
  if (navItems[map[raw]]) navItems[map[raw]].classList.add('active');
  _afterPageShow(raw);
});

function switchTab(tab, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tabpanel').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
}

// ── Connection check ─────────────────────────

async function checkConnection() {
  try {
    await apiFetch(CONFIG.ENDPOINTS.health);
    if (!isConnected) {
      isConnected = true;
      setConnected(true);
      fireAlert('ok', 'System Connected', 'TerraMetric is now receiving live sensor data.', 5000);
      fetchAll();
    }
  } catch {
    if (isConnected) {
      isConnected = false;
      setConnected(false);
      fireAlert('danger', 'Connection Lost', 'Cannot reach ' + API_BASE + ' — check the system is running.', 0);
    }
  }
}

function setConnected(on) {
  const dot   = document.getElementById('connDot');
  const label = document.getElementById('connLabel');
  const badge = document.getElementById('liveBadge');
  if (on) {
    dot.className     = 'status-dot online';
    label.textContent = 'SYSTEM ONLINE';
    badge.className   = 'badge badge-live';
    badge.textContent = '● Live';
  } else {
    dot.className     = 'status-dot';
    label.textContent = 'OFFLINE';
    badge.className   = 'badge badge-offline';
    badge.textContent = '● Offline';
  }
}

// ── Utility helpers ──────────────────────────

function setText(id, val) {
  const e = document.getElementById(id);
  if (e) e.textContent = val;
}

function showOffline(id) {
  const e = document.getElementById(id);
  if (e) e.textContent = '--';
}

function exportData() {
  if (!HIST.labels.length) { fireAlert('warning', 'No Data', 'No telemetry data to export yet.', 3000); return; }
  const rows = HIST.labels.map((l, i) =>
    `${l},${HIST.temp[i] ?? ''},${HIST.hum[i] ?? ''},${HIST.light[i] ?? ''},${HIST.height[i] ?? ''}`
  );
  downloadFile('terrametric-export.csv', 'Time,Temperature,Humidity,Light,Height\n' + rows.join('\n'), 'text/csv');
}

function downloadFile(name, content, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
}

// ── Boot sequence ────────────────────────────

populateGraphSampleSelect([]);
buildTrayList();
selectTray(0);
buildGalleryTabs();
buildGalleryTimeline();
showChartsOffline();

checkConnection();
setInterval(checkConnection, 10000);

if (typeof initSamplesRecordingUI === 'function') initSamplesRecordingUI();

applyRouteFromHash();

setInterval(() => { if (isConnected) fetchLatest(); },                                                        CONFIG.REFRESH_LIVE);
setInterval(() => { if (isConnected) { fetchTelemetry(); fetchAlerts(); fetchAnomalies(); fetchGallery(); } }, CONFIG.REFRESH_CHARTS);
setInterval(() => { if (isConnected) fetchAlerts(); },                                                        CONFIG.REFRESH_ALERTS);
