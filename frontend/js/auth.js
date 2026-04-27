// sessionStorage JWT for TerraMetric API (see /api/auth/login).
const AUTH_TOKEN_KEY = 'terrametric_access_token';

function getAccessToken() {
  try {
    return sessionStorage.getItem(AUTH_TOKEN_KEY);
  } catch (_) {
    return null;
  }
}

function setAccessToken(token) {
  sessionStorage.setItem(AUTH_TOKEN_KEY, token);
}

function clearAccessToken() {
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
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
  const headers = Object.assign({}, authHeaders(), init.headers || {});
  init.headers = headers;
  const res = await fetch(input, init);
  if (res.status === 401 && !isPublicAuthPage()) {
    clearAccessToken();
    window.location.href = 'login.html';
  }
  return res;
}
