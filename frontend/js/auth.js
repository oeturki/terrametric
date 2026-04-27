// JWT for TerraMetric API (see /api/auth/login).
// localStorage: shared across tabs (sessionStorage is not), so a second index.html tab
// still sends the same Bearer token after sign-in. Clear on sign-out to avoid cross-account bleed.
const AUTH_TOKEN_KEY = 'terrametric_access_token';

function getAccessToken() {
  try {
    const fromLocal = localStorage.getItem(AUTH_TOKEN_KEY);
    if (fromLocal) return fromLocal;
    // One-time read from old sessionStorage after upgrade
    const legacy = sessionStorage.getItem(AUTH_TOKEN_KEY);
    if (legacy) {
      localStorage.setItem(AUTH_TOKEN_KEY, legacy);
      sessionStorage.removeItem(AUTH_TOKEN_KEY);
    }
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch (_) {
    return null;
  }
}

function setAccessToken(token) {
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
  } catch (_) { /* private mode, etc. */ }
}

function clearAccessToken() {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
  } catch (_) { /* ignore */ }
}

function authHeaders(extra) {
  const h = Object.assign({}, extra || {});
  const t = getAccessToken();
  if (t) {
    h.Authorization = 'Bearer ' + t;
  }
  return h;
}

function isPublicAuthPage() {
  const p = String(window.location.pathname || '');
  return p.indexOf('login.html') >= 0 || p.indexOf('admin-register.html') >= 0;
}

/** fetch wrapper: attach Bearer token; on 401 clear token and redirect to login (SPA only). */
async function authFetch(input, init) {
  init = init || {};
  // Avoid stale GET responses (e.g. [] for /api/plants) after re-login when the URL is unchanged;
  // saving a sample uses POST (uncached) and the next GET then looked "fixed" — cache: no-store fixes that.
  if (init.cache === undefined) {
    init.cache = 'no-store';
  }
  const headers = Object.assign({}, authHeaders(), init.headers || {});
  init.headers = headers;
  const res = await fetch(input, init);
  if (res.status === 401 && !isPublicAuthPage()) {
    clearAccessToken();
    window.location.href = 'login.html';
  }
  return res;
}
