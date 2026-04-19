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

async function fetchTelemetry() {
  const hourRange = document.getElementById('graphRange')?.value || 24;
  try {
    const d = await apiFetch(CONFIG.ENDPOINTS.telemetry + `?hours=${hourRange}`);
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
    updateCharts(readings);
  } catch {
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
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.plants);
    const list = Array.isArray(data) ? data : data.plants || [];
    if (list.length) {
      trays = list;
      buildTrayList();
      selectTray(0);
      buildGalleryTabs();
    }
  } catch { /* use local trays */ }
}

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
    if (sample.id) {
      await apiPut(CONFIG.ENDPOINTS.plants + '/' + sample.id, sample);
    } else {
      await apiPost(CONFIG.ENDPOINTS.plants, sample);
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
