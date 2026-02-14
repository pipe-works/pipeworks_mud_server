/*
 * api.js
 *
 * Thin API client for the admin WebUI. Wraps fetch calls, injects session_id,
 * and provides typed helper methods for auth and admin endpoints.
 */

const DEFAULTS = {
  baseUrl: '',
  sessionKey: 'mud_admin_session',
};

/**
 * Create a shared fetch helper that normalizes JSON error responses.
 *
 * @param {string} baseUrl
 * @returns {Function}
 */
function buildFetcher(baseUrl) {
  return async function request(endpoint, options = {}) {
    const response = await fetch(`${baseUrl}${endpoint}`, options);
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      const text = await response.text();
      throw new Error(`Unexpected response (${response.status}): ${text}`);
    }
    const data = await response.json();
    if (!response.ok) {
      const message = data?.detail || data?.error || data?.message || 'Request failed.';
      throw new Error(message);
    }
    return data;
  };
}

/**
 * Session storage helpers.
 */
const Session = {
  read(config) {
    const settings = { ...DEFAULTS, ...config };
    const raw = sessionStorage.getItem(settings.sessionKey);
    return raw ? JSON.parse(raw) : null;
  },
  write(payload, config) {
    const settings = { ...DEFAULTS, ...config };
    sessionStorage.setItem(settings.sessionKey, JSON.stringify(payload));
  },
  clear(config) {
    const settings = { ...DEFAULTS, ...config };
    sessionStorage.removeItem(settings.sessionKey);
  },
};

/**
 * API client used by the admin WebUI.
 */
class ApiClient {
  constructor(config = {}) {
    this.config = { ...DEFAULTS, ...config };
    this.fetcher = buildFetcher(this.config.baseUrl);
  }

  /**
   * Authenticate and return session data.
   */
  async login({ username, password }) {
    return this.fetcher('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
  }

  /**
   * End the current session.
   */
  async logout(sessionId) {
    return this.fetcher('/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
  }
}

export { ApiClient, Session, DEFAULTS };
