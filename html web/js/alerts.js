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
// Call this from anywhere to trigger a notification.
// severity: 'warning' | 'danger' | 'info' | 'ok'
// dur: milliseconds before toast disappears (0 = stays until dismissed)

function fireAlert(sev, title, msg, dur = 6000) {
  const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const entry = { sev, title, msg, ts, id: Date.now() + Math.random() };

  alertLog.unshift(entry);
  renderAlertLog();
  updateBellCount();
  showToast(entry, dur);

  // Warning and danger also show the persistent banner
  if (sev === 'warning' || sev === 'danger') {
    showBanner(sev, title + (msg ? ' — ' + msg : ''));
  }

  // Shake all bell buttons
  document.querySelectorAll('.alert-bell-btn').forEach(b => {
    b.classList.remove('has-alerts');
    void b.offsetWidth; // force reflow to restart animation
    b.classList.add('has-alerts');
  });

  // Add to the recent alerts feed on the home page
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

// ── Persistent banner (below topbar) ─────────

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
    // Reset count when opened
    document.querySelectorAll('.bell-count').forEach(c => {
      c.textContent = '0';
      c.classList.remove('visible');
    });
    document.querySelectorAll('.alert-bell-btn').forEach(b => b.classList.remove('has-alerts'));
  }
}

// Close dropdown when clicking outside
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
