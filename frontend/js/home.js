// ─────────────────────────────────────────────
//  home.js — Home page stat cards, ESI gauge,
//            and Control Variables live readings
// ─────────────────────────────────────────────

// ── Update stat cards ────────────────────────

function _tempSubLine(d) {
  const t = d.temperature;
  if (t == null || isNaN(t)) return '—';
  const tmin = parseFloat(document.getElementById('temp-min')?.value);
  const tmax = parseFloat(document.getElementById('temp-max')?.value);
  const wlo = parseFloat(document.getElementById('warn-temp-lo')?.value);
  const wHi = parseFloat(document.getElementById('warn-temp')?.value);
  if (!isNaN(tmin) && t < tmin) return '⚠ Below desired min';
  if (!isNaN(tmax) && t > tmax) return '⚠ Above desired max';
  if (!isNaN(wlo) && t < wlo) return '⚠ Below tolerance (soft low)';
  if (!isNaN(wHi) && t > wHi) return '⚠ Above tolerance (soft high)';
  return '✓ In range';
}

function _tempVisualWarn(t) {
  if (t == null || isNaN(t)) return false;
  const tmin = parseFloat(document.getElementById('temp-min')?.value);
  const tmax = parseFloat(document.getElementById('temp-max')?.value);
  const wlo = parseFloat(document.getElementById('warn-temp-lo')?.value);
  const wHi = parseFloat(document.getElementById('warn-temp')?.value);
  if (!isNaN(tmin) && t < tmin) return true;
  if (!isNaN(tmax) && t > tmax) return true;
  if (!isNaN(wlo) && t < wlo) return true;
  if (!isNaN(wHi) && t > wHi) return true;
  return false;
}

function updateHomeStats(d) {
  const warnHum   = parseFloat(document.getElementById('warn-hum')?.value)   || 80;
  const warnLight = parseFloat(document.getElementById('warn-light')?.value) || 200;

  // Remove skeleton shimmer
  ['home-temp', 'home-hum', 'home-light', 'home-esi'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.remove('skel'); el.style.height = ''; el.style.width = ''; }
  });
  ['home-temp-sub', 'home-hum-sub', 'home-light-sub', 'home-esi-sub'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.remove('skel'); el.style.height = ''; el.style.width = ''; }
  });

  setText('home-temp',  d.temperature?.toFixed(1) + '°C');
  setText('home-hum',   d.humidity?.toFixed(1)    + '%');
  setText('home-light', Math.round(d.light)        + ' lux');

  setText('home-temp-sub',  _tempSubLine(d));
  setText('home-hum-sub',   d.humidity    > warnHum   ? '⚠ Above threshold' : '✓ Normal range');
  setText('home-light-sub', d.light       < warnLight ? '⚠ Low light'       : '✓ Adequate');

  const esi = calcESI(d);
  setText('home-esi', esi);
  setText('home-esi-sub', esi >= 75 ? '✓ Stable environment' : esi >= 50 ? '⚠ Moderate stress' : '🚨 High stress');
  updateESIGauge(esi);

  setLiveBadge('tempLive',   d.temperature?.toFixed(1) + '°C',   _tempVisualWarn(d.temperature));
  setLiveBadge('humLive',    d.humidity?.toFixed(1)    + '%',     d.humidity    > warnHum);
  setLiveBadge('lightLive',  Math.round(d.light)        + ' lux', d.light       < warnLight);
  setLiveBadge('heightLive', d.height?.toFixed(1)       + ' cm',  false);
}

function setLiveBadge(id, text, warn) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.style.color = warn ? 'var(--danger)' : 'var(--olive)';
}

// ── ESI — Environmental Stability Index ──────
// 0-100 score combining temp, humidity and light.
// Formula weights: temp 40%, humidity 30%, light 30%

function calcESI(d) {
  if (!d) return 0;
  const tw = 1 - Math.max(0, (d.temperature - 20)) / 20;
  const hw = 1 - Math.max(0, (d.humidity    - 50)) / 50;
  const lw = Math.min(1, d.light / 600);
  return Math.max(0, Math.min(100, Math.round((tw * 0.4 + hw * 0.3 + lw * 0.3) * 100)));
}

function updateESIGauge(esi) {
  const arc = document.getElementById('esiArc');
  if (!arc) return;
  arc.style.strokeDashoffset = 314 - (esi / 100) * 314;
  arc.style.stroke = esi >= 75 ? '#7a8c1e' : esi >= 50 ? '#c4711a' : '#a83232';
  setText('esiNum', esi);
  setText('esiStatus', esi >= 75 ? '🟢 Stable' : esi >= 50 ? '🟡 Moderate Stress' : '🔴 High Stress');
}

// ── Control Variables live readings ──────────

function updateControlLiveVals(d) {
  if (!d) return;
  const wh = parseFloat(document.getElementById('warn-hum')?.value)    || 80;
  const wl = parseFloat(document.getElementById('warn-light')?.value)  || 200;
  const wH = parseFloat(document.getElementById('warn-height')?.value) || 35;

  setLiveField('ctrl-temp',   d.temperature?.toFixed(1) + ' °C',  _tempVisualWarn(d.temperature));
  setLiveField('ctrl-hum',    d.humidity?.toFixed(1)    + ' %',   d.humidity    > wh);
  setLiveField('ctrl-light',  Math.round(d.light)       + ' lux', d.light       < wl);
  setLiveField('ctrl-height', d.height?.toFixed(1)      + ' cm',  d.height      > wH);
  setLiveField('ctrl-motion', d.motion ? '🟡 Detected'  : '🟢 Clear', false);
  setText('ctrl-cam', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
}

function setLiveField(id, text, warn) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = 'live-val connected' + (warn ? ' warn' : '');
}

// ── Reset control variables to defaults ──────

function resetDefaults() {
  const d = CONFIG.DEFAULTS;
  const wlo = document.getElementById('warn-temp-lo');
  if (wlo) wlo.value = d.temp_warn_lo != null && d.temp_warn_lo !== '' ? d.temp_warn_lo : '';
  document.getElementById('warn-temp').value   = d.temp_warn;
  document.getElementById('int-temp').value    = d.temp_int;
  document.getElementById('warn-hum').value    = d.hum_warn;
  document.getElementById('int-hum').value     = d.hum_interval;
  document.getElementById('warn-light').value  = d.light_warn;
  document.getElementById('int-light').value   = d.light_interval;
  document.getElementById('int-motion').value  = d.motion_interval;
  document.getElementById('warn-height').value = d.height_warn;
  document.getElementById('int-height').value  = d.height_interval;
  document.getElementById('warn-cam').value    = d.cam_schedule;
  document.getElementById('int-cam').value     = d.cam_interval;
  fireAlert('info', 'Defaults Restored', 'All thresholds reset to defaults. Hit Save to apply.', 5000);
}
