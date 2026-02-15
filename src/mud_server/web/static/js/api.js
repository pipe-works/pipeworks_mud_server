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

  /**
   * Fetch all users (admin only).
   */
  async getPlayers(sessionId) {
    return this.fetcher(`/admin/database/players?session_id=${sessionId}`);
  }

  /**
   * Fetch active sessions.
   */
  async getSessions(sessionId) {
    return this.fetcher(`/admin/database/sessions?session_id=${sessionId}`);
  }

  /**
   * Fetch active connections.
   */
  async getConnections(sessionId) {
    return this.fetcher(`/admin/database/connections?session_id=${sessionId}`);
  }

  /**
   * Fetch character locations.
   */
  async getLocations(sessionId) {
    return this.fetcher(`/admin/database/player-locations?session_id=${sessionId}`);
  }

  /**
   * Fetch recent chat messages.
   */
  async getChatMessages(sessionId, limit = 100) {
    const params = new URLSearchParams({ session_id: sessionId, limit: `${limit}` });
    return this.fetcher(`/admin/database/chat-messages?${params.toString()}`);
  }

  /**
   * Fetch table metadata.
   */
  async getTables(sessionId) {
    return this.fetcher(`/admin/database/tables?session_id=${sessionId}`);
  }

  /**
   * Fetch database schema relationships.
   */
  async getSchema(sessionId) {
    return this.fetcher(`/admin/database/schema?session_id=${sessionId}`);
  }

  /**
   * Fetch table rows for admin views.
   */
  async getTableRows(sessionId, tableName, limit = 100) {
    const params = new URLSearchParams({ session_id: sessionId, limit: `${limit}` });
    return this.fetcher(`/admin/database/table/${tableName}?${params.toString()}`);
  }

  /**
   * Fetch axis state for a character (admin only).
   */
  async getCharacterAxisState(sessionId, characterId) {
    return this.fetcher(`/admin/characters/${characterId}/axis-state?session_id=${sessionId}`);
  }

  /**
   * Fetch axis events for a character (admin only).
   */
  async getCharacterAxisEvents(sessionId, characterId, limit = 25) {
    const params = new URLSearchParams({ session_id: sessionId, limit: `${limit}` });
    return this.fetcher(`/admin/characters/${characterId}/axis-events?${params.toString()}`);
  }

  /**
   * Kick an active session.
   */
  async kickSession(sessionId, targetSessionId) {
    return this.fetcher('/admin/session/kick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, target_session_id: targetSessionId }),
    });
  }

  /**
   * Manage user accounts (role, ban, delete, password).
   */
  async manageUser(payload) {
    return this.fetcher('/admin/user/manage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  /**
   * Create a new user account (admin/superuser only).
   */
  async createUser(payload) {
    return this.fetcher('/admin/user/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  /**
   * Request server stop (superuser only).
   */
  async stopServer(sessionId) {
    return this.fetcher('/admin/server/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, confirm: true }),
    });
  }
}

export { ApiClient, Session, DEFAULTS };
