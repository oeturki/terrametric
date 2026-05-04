// ─────────────────────────────────────────────
//  home.js — Home page stat cards, ESI gauge,
//            and Control Variables live readings
// ─────────────────────────────────────────────

// ── Update stat cards ────────────────────────

/** Desired min/max, then tolerance low/high from Control inputs (same for temp, hum, light, PIR). */
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
  return _bandSubLine(d.temperature, 'temp-min', 'temp-max', 'warn-temp-low', 'warn-temp-high');
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
  return _bandVisualWarn(t, 'temp-min', 'temp-max', 'warn-temp-low', 'warn-temp-high');
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
  setText('home-hum-sub',   _bandSubLine(d.humidity, 'humid-min', 'humid-max', 'warn-hum-low', 'warn-hum-high'));
  setText('home-light-sub', _bandSubLine(d.light, 'light-min', 'light-max', 'warn-light-low', 'warn-light-high'));

  const esi = calcESI(d);
  setText('home-esi', esi);
  setText('home-esi-sub', esi >= 75 ? '✓ Stable environment' : esi >= 50 ? '⚠ Moderate stress' : '🚨 High stress');
  updateESIGauge(esi);

  setLiveBadge('tempLive',   d.temperature?.toFixed(1) + '°C',   _tempVisualWarn(d.temperature));
  setLiveBadge('humLive',    d.humidity?.toFixed(1)    + '%',     _bandVisualWarn(d.humidity, 'humid-min', 'humid-max', 'warn-hum-low', 'warn-hum-high'));
  setLiveBadge('lightLive',  Math.round(d.light)        + ' lux', _bandVisualWarn(d.light, 'light-min', 'light-max', 'warn-light-low', 'warn-light-high'));

  var hEl = document.getElementById('heightLive');
  if (hEl) {
    hEl.textContent = d.height != null && !isNaN(d.height) ? (d.height.toFixed(1) + ' cm') : '—';
    var tg = NaN;
    var htEl = document.getElementById('height-target');
    if (htEl && htEl.value !== '') tg = parseFloat(htEl.value);
    if (Number.isFinite(tg) && d.height != null && !isNaN(d.height) && d.height >= tg) {
      hEl.style.color = 'var(--sky)';
    } else {
      hEl.style.color = 'var(--olive)';
    }
  }
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

  setLiveField('ctrl-temp',   d.temperature?.toFixed(1) + ' °C',  _tempVisualWarn(d.temperature));
  setLiveField('ctrl-hum',    d.humidity?.toFixed(1)    + ' %',   _bandVisualWarn(d.humidity, 'humid-min', 'humid-max', 'warn-hum-low', 'warn-hum-high'));
  setLiveField('ctrl-light',  Math.round(d.light)       + ' lux', _bandVisualWarn(d.light, 'light-min', 'light-max', 'warn-light-low', 'warn-light-high'));

  var cHei = document.getElementById('ctrl-height');
  if (cHei) {
    cHei.textContent = d.height != null && !isNaN(d.height) ? (d.height.toFixed(1) + ' cm') : '—';
    var gx = '';
    var hte2 = document.getElementById('height-target');
    if (hte2) gx = hte2.value;
    var gNum = gx !== '' ? parseFloat(gx) : NaN;
    var met = Number.isFinite(gNum) && d.height != null && !isNaN(d.height) && d.height >= gNum;
    cHei.className = 'live-val connected' + (met ? ' height-met' : '');
  }

  setLiveField('ctrl-motion', d.motion ? '🟡 Detected' : '🟢 Clear', false);
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
  const tMn = document.getElementById('temp-min');
  if (tMn) tMn.value = d.temp_min != null ? d.temp_min : '';
  const tMx = document.getElementById('temp-max');
  if (tMx) tMx.value = d.temp_max != null ? d.temp_max : '';
  const wtLo = document.getElementById('warn-temp-low');
  if (wtLo) wtLo.value = d.temp_warn_low != null ? d.temp_warn_low : '';
  const wtHi = document.getElementById('warn-temp-high');
  if (wtHi) wtHi.value = d.temp_warn_high != null ? d.temp_warn_high : '';
  const intT = document.getElementById('int-temp');
  if (intT) intT.value = d.temp_int;

  const hMn = document.getElementById('humid-min');
  if (hMn) hMn.value = d.hum_min != null ? d.hum_min : '';
  const hMx = document.getElementById('humid-max');
  if (hMx) hMx.value = d.hum_max != null ? d.hum_max : '';
  const whLo = document.getElementById('warn-hum-low');
  if (whLo) whLo.value = d.hum_warn_low != null ? d.hum_warn_low : '';
  const whHi = document.getElementById('warn-hum-high');
  if (whHi) whHi.value = d.hum_warn_high != null ? d.hum_warn_high : '';
  const intH = document.getElementById('int-hum');
  if (intH) intH.value = d.hum_interval;

  const lMn = document.getElementById('light-min');
  if (lMn) lMn.value = d.light_min != null ? d.light_min : '';
  const lMx = document.getElementById('light-max');
  if (lMx) lMx.value = d.light_max != null ? d.light_max : '';
  const wlLo = document.getElementById('warn-light-low');
  if (wlLo) wlLo.value = d.light_warn_low != null ? d.light_warn_low : '';
  const wlHi = document.getElementById('warn-light-high');
  if (wlHi) wlHi.value = d.light_warn_high != null ? d.light_warn_high : '';
  const intL = document.getElementById('int-light');
  if (intL) intL.value = d.light_interval;

  const intM = document.getElementById('int-motion');
  if (intM) intM.value = d.motion_interval;

  const htg = document.getElementById('height-target');
  if (htg) htg.value = '';
  document.getElementById('int-height').value = d.height_interval;

  const camInt = document.getElementById('int-cam');
  if (camInt && camInt.tagName === 'SELECT') camInt.value = '1h';

  fireAlert('info', 'Defaults Restored', 'Locally reset to baseline values. Hit Save on Control Variables to apply on the server.', 5000);
}
