// ─────────────────────────────────────────────
//  home.js — Home page stat cards, ESI gauge,
//            and Control Variables live readings
// ─────────────────────────────────────────────

// ── Update stat cards ────────────────────────

/** Desired min/max, then soft low/high; same for temp, hum, light, height, and PIR (0/1). */
function _bandSubLine(v, minId, maxId, wloId, whiId) {
  if (v == null || (typeof v === 'number' && isNaN(v))) {
    return '—';
  }
  const tmin = parseFloat(document.getElementById(minId)?.value);
  const tmax = parseFloat(document.getElementById(maxId)?.value);
  const wlo = parseFloat(document.getElementById(wloId)?.value);
  const wHi = parseFloat(document.getElementById(whiId)?.value);
  if (!isNaN(tmin) && v < tmin) return '⚠ Below desired min';
  if (!isNaN(tmax) && v > tmax) return '⚠ Above desired max';
  if (!isNaN(wlo) && v < wlo) return '⚠ Below tolerance (soft low)';
  if (!isNaN(wHi) && v > wHi) return '⚠ Above tolerance (soft high)';
  return '✓ In range';
}

function _tempSubLine(d) {
  return _bandSubLine(d.temperature, 'temp-min', 'temp-max', 'warn-temp-lo', 'warn-temp');
}

function _bandVisualWarn(v, minId, maxId, wloId, whiId) {
  if (v == null || (typeof v === 'number' && isNaN(v))) return false;
  const tmin = parseFloat(document.getElementById(minId)?.value);
  const tmax = parseFloat(document.getElementById(maxId)?.value);
  const wlo = parseFloat(document.getElementById(wloId)?.value);
  const wHi = parseFloat(document.getElementById(whiId)?.value);
  if (!isNaN(tmin) && v < tmin) return true;
  if (!isNaN(tmax) && v > tmax) return true;
  if (!isNaN(wlo) && v < wlo) return true;
  if (!isNaN(wHi) && v > wHi) return true;
  return false;
}

function _tempVisualWarn(t) {
  return _bandVisualWarn(t, 'temp-min', 'temp-max', 'warn-temp-lo', 'warn-temp');
}

function updateHomeStats(d) {
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
  setText('home-hum-sub',   _bandSubLine(d.humidity, 'humid-min', 'humid-max', 'warn-hum-lo', 'warn-hum'));
  setText('home-light-sub', _bandSubLine(d.light, 'light-min', 'light-max', 'warn-light-lo', 'warn-light'));

  const esi = calcESI(d);
  setText('home-esi', esi);
  setText('home-esi-sub', esi >= 75 ? '✓ Stable environment' : esi >= 50 ? '⚠ Moderate stress' : '🚨 High stress');
  updateESIGauge(esi);

  setLiveBadge('tempLive',   d.temperature?.toFixed(1) + '°C',   _tempVisualWarn(d.temperature));
  setLiveBadge('humLive',    d.humidity?.toFixed(1)    + '%',     _bandVisualWarn(d.humidity, 'humid-min', 'humid-max', 'warn-hum-lo', 'warn-hum'));
  setLiveBadge('lightLive',  Math.round(d.light)        + ' lux', _bandVisualWarn(d.light, 'light-min', 'light-max', 'warn-light-lo', 'warn-light'));
  setLiveBadge('heightLive', d.height?.toFixed(1)       + ' cm',  _bandVisualWarn(d.height, 'height-min', 'height-max', 'warn-height-lo', 'warn-height'));
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
  // PIR maps to 0/1; soft band is optional [0,1] on Control (same order as other sensors).
  const m = d.motion == null ? NaN : (d.motion ? 1 : 0);

  setLiveField('ctrl-temp',   d.temperature?.toFixed(1) + ' °C',  _tempVisualWarn(d.temperature));
  setLiveField('ctrl-hum',    d.humidity?.toFixed(1)    + ' %',   _bandVisualWarn(d.humidity, 'humid-min', 'humid-max', 'warn-hum-lo', 'warn-hum'));
  setLiveField('ctrl-light',  Math.round(d.light)       + ' lux', _bandVisualWarn(d.light, 'light-min', 'light-max', 'warn-light-lo', 'warn-light'));
  setLiveField('ctrl-height', d.height?.toFixed(1)      + ' cm',  _bandVisualWarn(d.height, 'height-min', 'height-max', 'warn-height-lo', 'warn-height'));
  setLiveField('ctrl-motion', d.motion ? '🟡 Detected'  : '🟢 Clear', _bandVisualWarn(m, 'motion-min', 'motion-max', 'warn-motion-lo', 'warn-motion'));
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
  const hlo = document.getElementById('warn-hum-lo');
  if (hlo) hlo.value = d.hum_warn_lo != null && d.hum_warn_lo !== '' ? d.hum_warn_lo : '';
  document.getElementById('warn-hum').value    = d.hum_warn;
  document.getElementById('int-hum').value     = d.hum_interval;
  const llo = document.getElementById('warn-light-lo');
  if (llo) llo.value = d.light_warn_lo != null && d.light_warn_lo !== '' ? d.light_warn_lo : '';
  document.getElementById('warn-light').value  = d.light_warn;
  document.getElementById('int-light').value   = d.light_interval;
  const mlo = document.getElementById('warn-motion-lo');
  if (mlo) mlo.value = d.motion_warn_lo != null && d.motion_warn_lo !== '' ? d.motion_warn_lo : '';
  document.getElementById('warn-motion').value = d.motion_warn;
  document.getElementById('int-motion').value  = d.motion_interval;
  const ylo = document.getElementById('warn-height-lo');
  if (ylo) ylo.value = d.height_warn_lo != null && d.height_warn_lo !== '' ? d.height_warn_lo : '';
  document.getElementById('warn-height').value = d.height_warn;
  document.getElementById('int-height').value  = d.height_interval;
  document.getElementById('warn-cam').value    = d.cam_schedule;
  document.getElementById('int-cam').value     = d.cam_interval;
  fireAlert('info', 'Defaults Restored', 'All thresholds reset to defaults. Hit Save to apply.', 5000);
}
