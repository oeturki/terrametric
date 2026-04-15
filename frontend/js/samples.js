// ─────────────────────────────────────────────
//  samples.js — Manage Samples page +
//               Gallery growth timeline
// ─────────────────────────────────────────────

let trays = [{ name: '', loc: '', germ: '', notes: '', qr: 'TM-S001' }];
let selectedTray = 0;
let selectedGalleryPlant = 0;
let galleryPhotos = {}; // keyed by sample QR code

// ── Tray list ────────────────────────────────

function buildTrayList() {
  const container = document.getElementById('trayItems');
  if (!container) return;
  container.innerHTML = trays.map((t, i) => `
    <div class="tray-item ${i === selectedTray ? 'selected' : ''}" onclick="selectTray(${i})">
      <div class="tray-num">${i + 1}</div>
      <div>
        <div class="tray-item-name">${t.name || 'Unnamed Plant'}</div>
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
}

function addTray() {
  const n = trays.length + 1;
  trays.push({ name: '', loc: '', germ: '', notes: '', qr: 'TM-S' + n.toString().padStart(3, '0') });
  selectedTray = trays.length - 1;
  buildTrayList();
  selectTray(selectedTray);
  buildGalleryTabs();
  fireAlert('info', 'Sample Added', 'Sample ' + n + ' created. Fill in details and save.', 4000);
}

function removeTray() {
  if (trays.length <= 1) { fireAlert('warning', 'Cannot Remove', 'You must keep at least one sample.', 3000); return; }
  const name = trays[selectedTray].name || 'Sample ' + (selectedTray + 1);
  trays.splice(selectedTray, 1);
  selectedTray = Math.max(0, selectedTray - 1);
  if (selectedGalleryPlant >= trays.length) selectedGalleryPlant = 0;
  buildTrayList();
  selectTray(selectedTray);
  buildGalleryTabs();
  buildGalleryTimeline();
  fireAlert('info', 'Sample Removed', name + ' removed.', 3000);
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
