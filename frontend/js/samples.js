// ─────────────────────────────────────────────
//  samples.js — Manage Samples page +
//               Gallery growth timeline
// ─────────────────────────────────────────────

let trays = [{ name: '', loc: '', germ: '', notes: '', qr: 'TM-S001' }];
let selectedTray = 0;
let selectedGalleryPlant = 0;
let galleryPhotos = {}; // keyed by sample QR code

/** Set by /api/sessions/active — only one open session system-wide */
let activeRecordingSession = null;

/**
 * Smallest TM-S### not already used in `trays` (and optionally `extraQrs` from the server).
 * Avoids POST 409 when addTray used "length+1" while TM-S002 was already saved as id=7.
 */
function nextFreeTmQr(extraQrs) {
  const used = new Set();
  (trays || []).forEach(function (t) {
    const q = (t && t.qr && String(t.qr).trim()) || '';
    if (q) used.add(q.toUpperCase());
  });
  (extraQrs || []).forEach(function (q) {
    if (q) used.add(String(q).trim().toUpperCase());
  });
  var n = 1;
  var candidate;
  do {
    candidate = 'TM-S' + n.toString().padStart(3, '0');
    n += 1;
  } while (used.has(candidate.toUpperCase()));
  return candidate;
}

// ── Tray list ────────────────────────────────

function buildTrayList() {
  const container = document.getElementById('trayItems');
  if (!container) return;
  container.innerHTML = trays.map((t, i) => `
    <div class="tray-item ${i === selectedTray ? 'selected' : ''}" onclick="selectTray(${i})">
      <div class="tray-num">${i + 1}</div>
      <div>
        <div class="tray-item-name">${t.name || 'Unnamed Plant'}${activeRecordingSession && Number(activeRecordingSession.plant_id) === Number(t.id) ? ' <span class="status-dot online" style="display:inline-block;vertical-align:middle;width:8px;height:8px;" title="Recording telemetry"></span>' : ''}</div>
        <div class="tray-item-hint">${t.loc || 'No location set'}</div>
      </div>
    </div>`).join('') +
    `<div class="add-tray-row" onclick="addTray()">
      <div class="add-tray-icon">+</div>
      <span style="font-size:10px;">Add new sample…</span>
    </div>`;
}

function selectTray(i) {
  selectedTray = i;
  const t = trays[i];
  document.getElementById('detailTitle').textContent = `Sample Details — Sample ${i + 1}`;
  document.getElementById('d-name').value  = t.name  || '';
  document.getElementById('d-loc').value   = t.loc   || '';
  document.getElementById('d-germ').value  = t.germ  || '';
  document.getElementById('d-notes').value = t.notes || '';
  document.getElementById('d-qr').value    = t.qr    || '';
  buildTrayList();
  buildGalleryTabs();
  updateRecordingButtonState();
}

/**
 * Enable/disable the Start, Clear-telemetry, and Delete buttons based on whether
 * the currently-selected tray has been persisted server-side (has `id`).
 *
 * Single source of truth so we never end up with stale enabled state after
 * save/delete/select. Called from selectTray, saveSample success, refreshActiveRecording.
 */
function updateRecordingButtonState() {
  const t      = trays[selectedTray];
  const saved  = !!(t && t.id);
  const startBtn    = document.getElementById('btnStartRecording');
  const clearBtn    = document.getElementById('btnClearTelemetry');
  const delBtn      = document.getElementById('btnDeleteSample');
  const backfillBtn = document.getElementById('btnBackfillDummy');
  const isActiveForThis = !!(activeRecordingSession && Number(activeRecordingSession.plant_id) === Number(t && t.id));

  if (startBtn) {
    startBtn.disabled = !saved || isActiveForThis;
    startBtn.title = !saved
      ? 'Save the sample first to enable recording'
      : (isActiveForThis ? 'This sample is already recording' : 'Start a recording session for this sample');
  }
  if (clearBtn) {
    clearBtn.disabled = !saved;
    clearBtn.title = saved
      ? 'Delete this sample\u2019s telemetry rows. The sample itself is kept.'
      : 'Save the sample first.';
  }
  if (delBtn) {
    delBtn.disabled = !saved;
    delBtn.title = saved
      ? 'Permanently delete this sample, its telemetry and recording sessions'
      : 'Save the sample first.';
  }
  if (backfillBtn) {
    backfillBtn.disabled = !saved;
    backfillBtn.title = saved
      ? 'Insert hours of synthetic past readings tagged to this sample.'
      : 'Save the sample first.';
  }
}

function addTray() {
  const n = trays.length + 1;
  const qr = nextFreeTmQr();
  trays.push({ name: '', loc: '', germ: '', notes: '', qr: qr });
  selectedTray = trays.length - 1;
  buildTrayList();
  selectTray(selectedTray);
  buildGalleryTabs();
  fireAlert('info', 'Sample Added', 'Sample ' + n + ' created. Fill in details and save.', 4000);
}

/**
 * Locally remove an unsaved tray from the editor. For saved samples this is
 * a no-op safety guard — the user must use the explicit Delete button so the
 * destructive action goes through `confirmModal` and reaches the server.
 */
function removeTray() {
  if (trays.length <= 1) { fireAlert('warning', 'Cannot Remove', 'You must keep at least one sample.', 3000); return; }
  const t = trays[selectedTray];
  if (t && t.id) {
    fireAlert('info', 'Use Delete sample', 'This sample is saved server-side. Use the red \u201cDelete sample\u2026\u201d button below to remove it permanently.', 6000);
    return;
  }
  const name = t.name || 'Sample ' + (selectedTray + 1);
  trays.splice(selectedTray, 1);
  selectedTray = Math.max(0, selectedTray - 1);
  if (selectedGalleryPlant >= trays.length) selectedGalleryPlant = 0;
  buildTrayList();
  selectTray(selectedTray);
  buildGalleryTabs();
  buildGalleryTimeline();
  fireAlert('info', 'Sample Removed', name + ' removed (was unsaved).', 3000);
}

// ── Destructive lifecycle (clear telemetry / delete one / clear all) ──

/**
 * Wipe telemetry for the currently selected (saved) sample. The sample itself
 * stays so the user can keep recording later.
 */
async function clearSampleTelemetry() {
  const t = trays[selectedTray];
  if (!t || !t.id) { fireAlert('warning', 'Save first', 'Save this sample first.', 4000); return; }
  if (typeof apiDelete !== 'function') return;
  const ok = await confirmModal({
    title: 'Clear telemetry for this sample?',
    body:  'All sensor readings stored for <strong>' + (t.name || ('Sample ' + (selectedTray + 1))) +
           '</strong> will be permanently deleted. The sample record itself is kept. ' +
           'Any active recording for this sample will also be stopped.',
    danger: true,
    confirmText: 'Clear telemetry',
  });
  if (!ok) return;
  try {
    const res = await apiDelete(CONFIG.ENDPOINTS.plants + '/' + t.id + '/telemetry');
    fireAlert('ok', 'Telemetry cleared',
      (res && res.rows_deleted != null ? res.rows_deleted : 0) + ' readings removed for ' + (t.name || 'sample') + '.',
      4500);
    emitSamplesChanged('cleared', t.id);
    await refreshActiveRecording();
    if (typeof fetchTelemetry === 'function') fetchTelemetry();
  } catch (e) {
    fireAlert('warning', 'Clear failed', 'Could not reach server.', 5000);
  }
}

/**
 * Permanently delete the selected sample (and its telemetry/sessions) on the
 * server. Two confirmations: a destructive modal, then a typed confirmation
 * of the sample name to prevent slip-ups.
 */
async function deleteSampleFromServer() {
  const t = trays[selectedTray];
  if (!t || !t.id) { fireAlert('warning', 'Save first', 'This sample is not saved server-side; just use \u2212 to remove it.', 4000); return; }
  if (typeof apiDelete !== 'function') return;
  const labelName = t.name || ('Sample ' + (selectedTray + 1));

  const first = await confirmModal({
    title: 'Delete this sample?',
    body:  '<strong>' + labelName + '</strong> and ALL of its telemetry and recording sessions will be removed. ' +
           'This cannot be undone.',
    danger: true,
    confirmText: 'Continue',
  });
  if (!first) return;

  const second = await confirmModal({
    title: 'Final confirmation',
    body:  'Type the sample name <code>' + labelName + '</code> to confirm.',
    danger: true,
    confirmText: 'Delete forever',
    requireType: labelName,
  });
  if (!second) return;

  try {
    await apiDelete(CONFIG.ENDPOINTS.plants + '/' + t.id);
    const removedId = t.id;
    fireAlert('ok', 'Sample deleted', labelName + ' was removed permanently.', 4000);
    // Optimistic local removal — fetchSamples (via samples:changed) will reconcile.
    trays.splice(selectedTray, 1);
    if (!trays.length) trays.push({ name: '', loc: '', germ: '', notes: '', qr: nextFreeTmQr() });
    selectedTray = Math.max(0, Math.min(selectedTray, trays.length - 1));
    buildTrayList();
    selectTray(selectedTray);
    buildGalleryTabs();
    buildGalleryTimeline();
    emitSamplesChanged('deleted', removedId);
  } catch (e) {
    fireAlert('warning', 'Delete failed', 'Could not reach server.', 5000);
  }
}

/**
 * Wipe every sample on the server. Requires typing DELETE in the modal AND
 * the backend itself enforces ?confirm=DELETE so this is impossible to trigger
 * by accident from the API side either.
 */
async function clearAllSamples() {
  if (typeof apiDelete !== 'function') return;
  const ok = await confirmModal({
    title: 'Delete ALL samples?',
    body:  'This removes every sample, every telemetry row and every recording session in the database. ' +
           'There is no undo. Use this only when resetting the chamber for a new experiment.',
    danger: true,
    confirmText: 'Wipe everything',
    requireType: 'DELETE',
  });
  if (!ok) return;
  try {
    const res = await apiDelete(CONFIG.ENDPOINTS.plants + '?confirm=DELETE');
    fireAlert('ok', 'All samples deleted',
      (res && res.removed != null ? res.removed : 0) + ' samples removed. The chamber is now empty.',
      5000);
    trays = [{ name: '', loc: '', germ: '', notes: '', qr: 'TM-S001' }];
    selectedTray = 0;
    selectedGalleryPlant = 0;
    buildTrayList();
    selectTray(0);
    buildGalleryTabs();
    buildGalleryTimeline();
    emitSamplesChanged('wiped', null);
  } catch (e) {
    fireAlert('warning', 'Bulk delete failed', 'Could not reach server, or confirm token rejected.', 6000);
  }
}

function clearDetail() {
  ['d-name', 'd-loc', 'd-germ', 'd-notes', 'd-qr'].forEach(id => document.getElementById(id).value = '');
}

async function exportSamples() {
  const csv = [
    'Name,Location,Germination,QR,Notes',
    ...trays.map(t => `"${t.name}","${t.loc}","${t.germ}","${t.qr}","${t.notes}"`)
  ].join('\n');
  downloadFile('terrametric-samples.csv', csv, 'text/csv');
}

// ── Gallery tabs ─────────────────────────────

function buildGalleryTabs() {
  const tabs = document.getElementById('galleryPlantTabs');
  if (!tabs) return;
  tabs.innerHTML = trays.map((t, i) => `
    <div class="plant-tab ${i === selectedGalleryPlant ? 'active' : ''}" onclick="setGalleryPlant(${i})">
      ${t.name || 'Sample ' + (i + 1)}
      <span style="opacity:.55;font-size:9px;">#${i + 1}</span>
    </div>`).join('');
}

function setGalleryPlant(i) {
  selectedGalleryPlant = i;
  buildGalleryTabs();
  buildGalleryTimeline();
}

// ── Gallery timeline ──────────────────────────

function buildGalleryTimeline() {
  const header   = document.getElementById('galleryPlantHeader');
  const timeline = document.getElementById('galleryTimeline');
  if (!header || !timeline) return;

  const plant      = trays[selectedGalleryPlant];
  if (!plant) return;

  const photos      = galleryPhotos[plant.qr] || [];
  const photoCount  = photos.length;
  const latestHeight = photoCount ? photos[0].height_cm : null;
  const firstHeight  = photoCount ? photos[photos.length - 1].height_cm : null;
  const growth = (latestHeight && firstHeight) ? (latestHeight - firstHeight).toFixed(1) : '--';

  header.innerHTML = `
    <div class="gallery-header" style="margin-bottom:20px;">
      <div style="font-size:48px;flex-shrink:0;">🌿</div>
      <div style="flex:1;">
        <div style="font-family:'Syne',sans-serif;font-weight:800;font-size:16px;margin-bottom:3px;">${plant.name || 'Unnamed Plant'}</div>
        <div style="font-size:10px;color:var(--bark-mid);margin-bottom:10px;">📍 ${plant.loc || 'No location'} &nbsp;·&nbsp; 🏷 ${plant.qr}</div>
        <div style="display:flex;gap:20px;flex-wrap:wrap;">
          <div class="gallery-meta-stat"><div class="gallery-meta-label">Current Height</div><div class="gallery-meta-val" style="color:var(--olive)">${latestHeight ? latestHeight + ' cm' : '--'}</div></div>
          <div class="gallery-meta-stat"><div class="gallery-meta-label">Total Growth</div><div class="gallery-meta-val" style="color:var(--sky)">${growth !== '--' ? '+' + growth + ' cm' : '--'}</div></div>
          <div class="gallery-meta-stat"><div class="gallery-meta-label">Photos Captured</div><div class="gallery-meta-val">${photoCount}</div></div>
          <div class="gallery-meta-stat"><div class="gallery-meta-label">Germinated</div><div class="gallery-meta-val" style="font-size:13px;">${plant.germ ? new Date(plant.germ).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '--'}</div></div>
        </div>
      </div>
    </div>`;

  if (!photoCount) {
    timeline.innerHTML = `
      <div class="no-photos">
        <div class="no-photos-icon">📷</div>
        <div style="font-family:'Syne',sans-serif;font-weight:700;font-size:13px;color:var(--bark-mid);margin-bottom:8px;">No photos yet</div>
        <div style="font-size:11px;color:var(--bark-mid);line-height:1.7;">
          Photos will appear here automatically once the camera starts capturing.<br>
          Make sure the QR code <strong>${plant.qr}</strong> is assigned to this plant.
        </div>
      </div>`;
    return;
  }

  const byDay = {};
  photos.forEach(p => {
    const day = new Date(p.timestamp).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    if (!byDay[day]) byDay[day] = [];
    byDay[day].push(p);
  });

  timeline.innerHTML = Object.entries(byDay).map(([day, dayPhotos]) => `
    <div class="day-section">
      <div class="day-label">${day}</div>
      <div class="day-grid">
        ${dayPhotos.map(p => {
          const t = new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          const imgContent = p.image_url
            ? `<img src="${p.image_url}" style="width:100%;height:100%;object-fit:cover;" alt="Plant photo">`
            : `<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:40px;background:#e8f5e8;">🌿</div>`;
          return `
            <div class="photo-card">
              <div class="photo-thumb" style="position:relative;overflow:hidden;">
                ${imgContent}
                ${p.height_cm ? `<div class="photo-height-tag">${p.height_cm} cm</div>` : ''}
              </div>
              <div class="photo-info">
                <div class="photo-name">${plant.name?.split(' ')[0] || 'Plant'}</div>
                <div class="photo-dt">🕐 ${t}</div>
              </div>
            </div>`;
        }).join('')}
      </div>
    </div>`).join('');
}

// ── Telemetry recording (one active sample system-wide) ─────────────────

/**
 * @param {number|string|null} preferId — after registering, select this device in the dropdown
 */
async function loadDevicesForSamples(preferId) {
  const sel = document.getElementById('d-device');
  if (!sel || typeof apiFetch !== 'function') return;
  try {
    const d = await apiFetch(CONFIG.ENDPOINTS.devices);
    const list = Array.isArray(d.devices) ? d.devices : [];
    const want = preferId != null && preferId !== '' ? String(preferId) : sel.value;
    sel.innerHTML = '<option value="">— None (optional) —</option>' + list.map(dev => {
      const label = (dev.label || dev.bt_name || ('Device ' + dev.id)).replace(/</g, '');
      return '<option value="' + dev.id + '">' + label + '</option>';
    }).join('');
    if (want && [...sel.options].some(function (o) { return o.value === want; })) sel.value = want;
  } catch (e) { /* offline */ }
}

async function registerSampleDevice() {
  const btEl = document.getElementById('d-dev-bt');
  const labEl = document.getElementById('d-dev-label');
  const macEl = document.getElementById('d-dev-mac');
  const btn = document.getElementById('btnRegisterDevice');
  const bt = (btEl && btEl.value || '').trim();
  if (!bt) {
    fireAlert('warning', 'Bluetooth name required', 'Enter the name configured on your module (e.g. Group14).', 4000);
    return;
  }
  if (typeof apiPost !== 'function') return;
  const payload = { bt_name: bt };
  const lab = (labEl && labEl.value || '').trim();
  const mac = (macEl && macEl.value || '').trim();
  if (lab) payload.label = lab;
  if (mac) payload.mac = mac;
  if (btn) { btn.disabled = true; }
  try {
    const created = await apiPost(CONFIG.ENDPOINTS.devices, payload);
    fireAlert('ok', 'Device registered', (created.label || created.bt_name || 'Device') + ' — you can select it above.', 5000);
    if (btEl) btEl.value = '';
    if (labEl) labEl.value = '';
    if (macEl) macEl.value = '';
    await loadDevicesForSamples(created && created.id != null ? created.id : null);
  } catch (e) {
    fireAlert('warning', 'Registration failed', 'Check the server is running. MAC must be unique if set.', 6000);
  } finally {
    if (btn) { btn.disabled = false; }
  }
}

async function refreshActiveRecording() {
  const st = document.getElementById('recordingStatus');
  const startBtn = document.getElementById('btnStartRecording');
  const stopBtn = document.getElementById('btnStopRecording');
  if (typeof apiFetch !== 'function') return;
  try {
    const d = await apiFetch(CONFIG.ENDPOINTS.sessionsActive);
    const sessions = Array.isArray(d.sessions) ? d.sessions : [];
    activeRecordingSession = sessions[0] || null;
    if (st) {
      if (activeRecordingSession) {
        const dummy = activeRecordingSession.dummy_stream
          ? ' (DUMMY: ' + (activeRecordingSession.scenario || 'stable') +
            ' @ ' + (activeRecordingSession.stream_interval_sec || 5) + 's)'
          : '';
        st.textContent = 'Recording: session #' + activeRecordingSession.id +
          ' \u2192 plant #' + activeRecordingSession.plant_id + dummy + '. Stop when finished.';
        st.style.color = 'var(--olive)';
      } else {
        st.textContent = 'Recording: not active \u2014 start when this tray should receive sensor data.';
        st.style.color = 'var(--bark-mid)';
      }
    }
    if (stopBtn) stopBtn.disabled = !activeRecordingSession;
  } catch (e) {
    activeRecordingSession = null;
    if (st) {
      st.textContent = 'Recording: could not reach server.';
      st.style.color = 'var(--bark-mid)';
    }
    if (stopBtn) stopBtn.disabled = true;
  }
  buildTrayList();
  updateRecordingButtonState();
}

async function startSampleRecording() {
  const t = trays[selectedTray];
  if (!t || !t.id) {
    fireAlert('warning', 'Save first', 'Save this sample to the server so it has an ID before recording.', 5000);
    return;
  }
  const devSel = document.getElementById('d-device');
  const scenarioEl = document.getElementById('d-scenario');
  const dummyEl = document.getElementById('d-dummy-stream');
  const intervalEl = document.getElementById('d-stream-interval');

  const payload = { plant_id: t.id };
  if (devSel && devSel.value) payload.device_id = parseInt(devSel.value, 10);
  payload.scenario           = (scenarioEl && scenarioEl.value) || 'stable';
  payload.dummy_stream       = !!(dummyEl && dummyEl.checked);
  payload.stream_interval_sec = Math.max(1, Math.min(300,
    parseInt((intervalEl && intervalEl.value) || '5', 10) || 5));

  try {
    if (typeof apiPost !== 'function') throw new Error('api');
    await apiPost(CONFIG.ENDPOINTS.sessionsStart, payload);
    const tail = payload.dummy_stream
      ? ' Dummy data engine running scenario \u201c' + payload.scenario + '\u201d every ' + payload.stream_interval_sec + 's.'
      : '';
    fireAlert('ok', 'Recording started',
      'Starting a new recording ends any other active recording. Telemetry tags to this sample until you stop.' + tail,
      5500);
    if (payload.dummy_stream && typeof setGraphSampleForPlant === 'function') {
      setGraphSampleForPlant(t.id);
    }
    await refreshActiveRecording();
    if (typeof fetchTelemetry === 'function') fetchTelemetry();
  } catch (e) {
    fireAlert('warning', 'Could not start', 'Check the server. If another sample was recording, try again.', 5000);
  }
}

/**
 * Insert hours of back-dated synthetic readings stamped to this sample so the
 * graphs/anomaly pages have something to show without waiting for live data.
 * Asks the user for hours / scenario / interval through the same modal helper
 * as destructive actions (consistent UX, no native prompts).
 */
async function backfillDummyHistory() {
  const t = trays[selectedTray];
  if (!t || !t.id) { fireAlert('warning', 'Save first', 'Save this sample first.', 4000); return; }
  if (typeof apiPost !== 'function') return;

  // Build the form node so confirmModal renders our pickers inline.
  const form = document.createElement('div');
  form.innerHTML = '' +
    '<div style="display:grid;gap:8px;font-size:12px;">' +
      '<label>Hours of history' +
        '<select id="bf-hours" style="width:100%;padding:6px 8px;margin-top:4px;border:1px solid rgba(0,0,0,.2);border-radius:6px;">' +
          '<option value="1">1 hour</option>' +
          '<option value="6">6 hours</option>' +
          '<option value="24" selected>24 hours</option>' +
          '<option value="72">72 hours (3 days)</option>' +
          '<option value="168">168 hours (1 week)</option>' +
        '</select>' +
      '</label>' +
      '<label>Scenario' +
        '<select id="bf-scenario" style="width:100%;padding:6px 8px;margin-top:4px;border:1px solid rgba(0,0,0,.2);border-radius:6px;">' +
          '<option value="stable">Stable</option>' +
          '<option value="heat_spike" selected>Heat spike (anomaly fodder)</option>' +
          '<option value="drought">Drought</option>' +
          '<option value="cold_night">Cold night</option>' +
          '<option value="sensor_drift">Sensor drift</option>' +
        '</select>' +
      '</label>' +
      '<label>Sample every (seconds)' +
        '<input type="number" id="bf-interval" min="5" max="3600" value="60" style="width:100%;padding:6px 8px;margin-top:4px;border:1px solid rgba(0,0,0,.2);border-radius:6px;">' +
      '</label>' +
      '<div style="font-size:11px;color:var(--bark-mid);margin-top:4px;line-height:1.5;">' +
        'These rows are inserted in one transaction and tagged directly to <strong>' + (t.name || ('Sample ' + (selectedTray + 1))) + '</strong>. ' +
        'They appear in the Graphs page immediately. Use Clear telemetry to remove them later.' +
      '</div>' +
    '</div>';

  const ok = await confirmModal({
    title: 'Backfill dummy history',
    body: form,
    confirmText: 'Generate',
  });
  if (!ok) return;

  const hours = parseInt(form.querySelector('#bf-hours').value, 10);
  const scenario = form.querySelector('#bf-scenario').value;
  const interval = Math.max(5, Math.min(3600, parseInt(form.querySelector('#bf-interval').value, 10) || 60));

  try {
    const res = await apiPost(CONFIG.ENDPOINTS.dummyBackfill, {
      plant_id: t.id, hours: hours, scenario: scenario, interval_sec: interval,
    });
    fireAlert('ok', 'Backfill complete',
      (res && res.rows_inserted != null ? res.rows_inserted : 0) +
      ' synthetic rows added to ' + (t.name || 'this sample') + ' (scenario: ' + scenario + ', span: ' + hours + ' h).',
      6000);
    emitSamplesChanged('cleared', t.id); // graphs/anomalies should re-pull
    if (typeof setGraphSampleForPlant === 'function') setGraphSampleForPlant(t.id);
    if (typeof fetchTelemetry === 'function') fetchTelemetry();
  } catch (e) {
    fireAlert('warning', 'Backfill failed', 'Check the server is reachable and the sample is saved.', 5000);
  }
}

async function stopSampleRecording() {
  if (!activeRecordingSession || typeof apiPostNoBody !== 'function') return;
  try {
    await apiPostNoBody('/api/sessions/' + activeRecordingSession.id + '/stop');
    fireAlert('ok', 'Recording stopped', 'Stored readings stay linked to this sample for analysis.', 4000);
    await refreshActiveRecording();
  } catch (e) {
    fireAlert('warning', 'Could not stop', 'Check connection.', 5000);
  }
}

/** Called from app.js after api.js loads */
function initSamplesRecordingUI() {
  loadDevicesForSamples();
  refreshActiveRecording();
  setInterval(refreshActiveRecording, 10000);
}

window.addEventListener("samples:changed", function () {
  if (typeof buildControlPlantSelectFromList === "function") {
    buildControlPlantSelectFromList(trays);
  }
  // Server sync + control reload: see api.js fetchSamples (also on samples:changed) which awaits fetchControls.
});
