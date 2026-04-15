// ─────────────────────────────────────────────
//  app.js — Navigation, connection check,
//           utility helpers, and boot sequence
// ─────────────────────────────────────────────

let isConnected = false;

// ── Page navigation ──────────────────────────

function goTo(page, navEl) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  if (navEl) navEl.classList.add('active');
  if (page === 'samples')  buildTrayList();
  if (page === 'viewdata') buildGalleryTabs();
}

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

buildTrayList();
selectTray(0);
buildGalleryTabs();
buildGalleryTimeline();
showChartsOffline();

checkConnection();
setInterval(checkConnection, 10000);

setInterval(() => { if (isConnected) fetchLatest(); },                                                        CONFIG.REFRESH_LIVE);
setInterval(() => { if (isConnected) { fetchTelemetry(); fetchAlerts(); fetchAnomalies(); fetchGallery(); } }, CONFIG.REFRESH_CHARTS);
setInterval(() => { if (isConnected) fetchAlerts(); },                                                        CONFIG.REFRESH_ALERTS);
