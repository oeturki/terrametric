// ─────────────────────────────────────────────
//  alerts.js — Global alert & notification system
//  Handles toasts, the bell icon, the dropdown
//  log, and the persistent warning banner.
// ─────────────────────────────────────────────

const SEV = {
  warning: { icon: '⚠',  label: 'WARNING'  },
  danger:  { icon: '🚨', label: 'CRITICAL' },
  info:    { icon: 'ℹ',  label: 'INFO'     },
  ok:      { icon: '✅', label: 'OK'       },
};

let alertLog = [];
let ddOpen = false;

// ── Fire an alert ────────────────────────────
// severity: 'warning' | 'danger' | 'info' | 'ok'
// dur: ms before toast disappears (0 = stays until dismissed)

function fireAlert(sev, title, msg, dur = 6000) {
  const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const entry = { sev, title, msg, ts, id: Date.now() + Math.random() };

  alertLog.unshift(entry);
  renderAlertLog();
  updateBellCount();
  showToast(entry, dur);

  if (sev === 'warning' || sev === 'danger') {
    showBanner(sev, title + (msg ? ' — ' + msg : ''));
  }

  document.querySelectorAll('.alert-bell-btn').forEach(b => {
    b.classList.remove('has-alerts');
    void b.offsetWidth;
    b.classList.add('has-alerts');
  });

  const feed = document.getElementById('alertFeed');
  if (feed) {
    const item = document.createElement('div');
    item.className = 'feed-item ' + sev;
    item.innerHTML = `
      <div class="feed-icon">${SEV[sev].icon}</div>
      <div>
        <div class="feed-title">${title}</div>
        <div class="feed-time">${ts}${msg ? ' — ' + msg : ''}</div>
      </div>`;
    feed.prepend(item);
    while (feed.children.length > 4) feed.lastChild.remove();
    feed.querySelector('[style="font-size:10px;color:var(--bark-mid);padding:8px 0;"]')?.remove();
  }
}

// ── Toast notification ───────────────────────

function showToast(entry, dur) {
  const stack = document.getElementById('toastStack');
  const el = document.createElement('div');
  el.className = 'toast ' + entry.sev;
  el.style.setProperty('--dur', (dur / 1000) + 's');
  el.innerHTML = `
    <div class="toast-icon">${SEV[entry.sev].icon}</div>
    <div class="toast-body">
      <div class="toast-title">${entry.title}</div>
      ${entry.msg ? `<div class="toast-msg">${entry.msg}</div>` : ''}
      <div class="toast-time">${entry.ts}</div>
    </div>
    <div class="toast-close" onclick="dismissToast(this.closest('.toast'))">✕</div>`;
  stack.appendChild(el);
  if (dur > 0) setTimeout(() => dismissToast(el), dur);
}

function dismissToast(el) {
  if (!el || el.classList.contains('exiting')) return;
  el.classList.add('exiting');
  setTimeout(() => el.remove(), 290);
}

// ── Persistent banner ─────────────────────────

function showBanner(sev, text) {
  document.querySelectorAll('.persistent-banner').forEach(b => {
    b.className = 'persistent-banner visible' + (sev === 'danger' ? ' critical' : '');
    const bt = b.querySelector('.banner-text');
    if (bt) bt.textContent = text;
  });
}

function dismissBanner() {
  document.querySelectorAll('.persistent-banner').forEach(b => b.classList.remove('visible'));
}

// ── Bell dropdown ────────────────────────────

function toggleDD() {
  const dd = document.getElementById('alertDD');
  ddOpen = !ddOpen;
  dd.classList.toggle('open', ddOpen);
  if (ddOpen) {
    document.querySelectorAll('.bell-count').forEach(c => {
      c.textContent = '0';
      c.classList.remove('visible');
    });
    document.querySelectorAll('.alert-bell-btn').forEach(b => b.classList.remove('has-alerts'));
  }
}

document.addEventListener('click', e => {
  if (ddOpen && !e.target.closest('.alert-dropdown') && !e.target.closest('.alert-bell-btn')) {
    document.getElementById('alertDD').classList.remove('open');
    ddOpen = false;
  }
});

function updateBellCount() {
  const c = alertLog.filter(a => a.sev === 'warning' || a.sev === 'danger').length;
  document.querySelectorAll('.bell-count').forEach(bc => {
    bc.textContent = c > 9 ? '9+' : c;
    bc.classList.toggle('visible', c > 0);
  });
}

/**
 * Home page "Recent Alerts" — always show latest server state (not gated by toast deduplication).
 */
function renderHomeAlertFeedFromServer(alerts) {
  const feed = document.getElementById('alertFeed');
  if (!feed) return;
  feed.innerHTML = '';
  if (!alerts || !alerts.length) {
    const ph = document.createElement('div');
    ph.style.cssText = 'font-size:10px;color:var(--bark-mid);padding:8px 0;';
    ph.textContent = 'No active alerts from the server';
    feed.appendChild(ph);
    return;
  }
  alerts.slice(0, 5).forEach(a => {
    const sev = a.severity === 'danger' ? 'danger' : (a.severity === 'info' ? 'info' : 'warning');
    const item = document.createElement('div');
    item.className = 'feed-item ' + sev;
    const ts = a.timestamp
      ? new Date(a.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      : '';
    const icon = (SEV[sev] && SEV[sev].icon) || '⚠';
    const title = (a.title != null && a.title !== '') ? a.title : (a.message ? String(a.message).slice(0, 40) : 'Alert');
    const sub = a.message && a.title && a.message !== a.title ? a.message : (a.message || '');
    item.innerHTML = `
      <div class="feed-icon">${icon}</div>
      <div>
        <div class="feed-title">${title}</div>
        <div class="feed-time">${ts}${sub && sub !== title ? ' — ' + sub : ''}</div>
      </div>`;
    feed.appendChild(item);
  });
}

/**
 * Bell dropdown: mirror active server alerts so the list matches the API even when toasts are deduped.
 */
function syncServerAlertsToDropdown(alerts) {
  if (!Array.isArray(alerts)) return;
  alertLog.length = 0;
  alerts.slice(0, 30).forEach(a => {
    const sev = a.severity === 'danger' ? 'danger' : (a.severity === 'info' ? 'info' : 'warning');
    const ts = a.timestamp
      ? new Date(a.timestamp).toLocaleString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    alertLog.push({
      sev: sev,
      title: a.title || a.variable || 'Alert',
      msg: a.message || '',
      ts: ts,
      id: a.id != null ? 'srv-' + a.id : Date.now() + Math.random()
    });
  });
  renderAlertLog();
  updateBellCount();
}

function renderAlertLog() {
  const log = document.getElementById('alertLog');
  const empty = document.getElementById('logEmpty');
  if (!alertLog.length) { empty.style.display = 'block'; return; }
  empty.style.display = 'none';
  log.querySelectorAll('.log-item').forEach(e => e.remove());
  alertLog.slice(0, 30).forEach(e => {
    const el = document.createElement('div');
    el.className = 'log-item';
    el.innerHTML = `
      <div class="log-icon">${SEV[e.sev].icon}</div>
      <div class="log-body">
        <div class="log-title">${e.title}</div>
        <div class="log-msg">${e.msg || ''}</div>
        <div class="log-time">${e.ts}</div>
      </div>
      <div class="log-sev ${e.sev}">${SEV[e.sev].label}</div>`;
    log.appendChild(el);
  });
}

function clearAlerts() {
  alertLog.length = 0;
  renderAlertLog();
  updateBellCount();
  dismissBanner();
  document.getElementById('logEmpty').style.display = 'block';
}

// ── Destructive-action confirm modal ─────────────
//
// Async helper so destructive UI flows read top-to-bottom:
//
//   if (!await confirmModal({title, body, danger:true})) return;
//
// `requireType` (optional) forces the user to type a token (e.g. 'DELETE')
// to enable Confirm — used for irreversible bulk wipes.

let _modalStylesInjected = false;
function _injectModalStyles() {
  if (_modalStylesInjected) return;
  _modalStylesInjected = true;
  const css = `
    .tm-modal-overlay{position:fixed;inset:0;background:rgba(20,18,14,.55);backdrop-filter:blur(2px);
      display:flex;align-items:center;justify-content:center;z-index:9999;animation:tmFade .12s ease-out;}
    .tm-modal{background:var(--bg,#fffaf2);color:var(--bark-dark,#322a1f);border-radius:10px;
      box-shadow:0 24px 60px rgba(0,0,0,.35);max-width:440px;width:calc(100% - 32px);
      padding:22px 22px 18px;font-family:system-ui,sans-serif;border:1px solid rgba(0,0,0,.08);}
    .tm-modal__title{font-family:'Syne',sans-serif;font-weight:800;font-size:16px;margin:0 0 8px;
      letter-spacing:.02em;}
    .tm-modal__body{font-size:13px;line-height:1.55;color:var(--bark-mid,#5a4f3f);margin-bottom:14px;}
    .tm-modal__type-row{margin-bottom:14px;}
    .tm-modal__type-row label{display:block;font-size:11px;color:var(--bark-mid,#5a4f3f);
      text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;}
    .tm-modal__type-row input{width:100%;padding:8px 10px;font-family:'DM Mono',monospace;font-size:13px;
      border:1px solid rgba(0,0,0,.18);border-radius:6px;background:#fff;}
    .tm-modal__actions{display:flex;gap:10px;justify-content:flex-end;}
    .tm-modal__actions .btn{min-width:90px;}
    .tm-modal__btn-danger{background:#b8392b;color:#fff;border:1px solid #8a2818;}
    .tm-modal__btn-danger:hover:not(:disabled){background:#9b2f24;}
    .tm-modal__btn-danger:disabled{opacity:.45;cursor:not-allowed;}
    @keyframes tmFade{from{opacity:0}to{opacity:1}}`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
}

function confirmModal(opts) {
  _injectModalStyles();
  const title       = (opts && opts.title) || 'Are you sure?';
  const body        = (opts && opts.body) || '';
  const danger      = !!(opts && opts.danger);
  const confirmText = (opts && opts.confirmText) || (danger ? 'Delete' : 'Confirm');
  const cancelText  = (opts && opts.cancelText) || 'Cancel';
  const requireType = opts && opts.requireType ? String(opts.requireType) : null;

  return new Promise(function (resolve) {
    const overlay = document.createElement('div');
    overlay.className = 'tm-modal-overlay';

    const modal = document.createElement('div');
    modal.className = 'tm-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');

    const h = document.createElement('h3');
    h.className = 'tm-modal__title';
    h.textContent = title;
    modal.appendChild(h);

    const p = document.createElement('div');
    p.className = 'tm-modal__body';
    if (body instanceof Node) p.appendChild(body); else p.innerHTML = body;
    modal.appendChild(p);

    let typeInput = null;
    if (requireType) {
      const row = document.createElement('div');
      row.className = 'tm-modal__type-row';
      const lbl = document.createElement('label');
      lbl.textContent = 'Type ' + requireType + ' to confirm';
      typeInput = document.createElement('input');
      typeInput.type = 'text';
      typeInput.autocomplete = 'off';
      typeInput.spellcheck = false;
      typeInput.placeholder = requireType;
      row.appendChild(lbl);
      row.appendChild(typeInput);
      modal.appendChild(row);
    }

    const actions = document.createElement('div');
    actions.className = 'tm-modal__actions';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn-ghost';
    cancelBtn.textContent = cancelText;
    const okBtn = document.createElement('button');
    okBtn.type = 'button';
    okBtn.className = 'btn ' + (danger ? 'tm-modal__btn-danger' : 'btn-primary');
    okBtn.textContent = confirmText;
    actions.appendChild(cancelBtn);
    actions.appendChild(okBtn);
    modal.appendChild(actions);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    function close(result) {
      document.removeEventListener('keydown', onKey, true);
      overlay.remove();
      resolve(result);
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.stopPropagation(); close(false); }
      if (e.key === 'Enter' && !okBtn.disabled) { e.stopPropagation(); close(true); }
    }
    document.addEventListener('keydown', onKey, true);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close(false);
    });
    cancelBtn.addEventListener('click', function () { close(false); });
    okBtn.addEventListener('click', function () { close(true); });

    if (typeInput) {
      okBtn.disabled = true;
      typeInput.addEventListener('input', function () {
        okBtn.disabled = typeInput.value !== requireType;
      });
      setTimeout(function () { typeInput.focus(); }, 30);
    } else {
      setTimeout(function () { okBtn.focus(); }, 30);
    }
  });
}