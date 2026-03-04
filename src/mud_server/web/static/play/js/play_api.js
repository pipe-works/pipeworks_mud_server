/*
 * play_api.js
 *
 * API transport helpers for the play shell.
 */

/**
 * Normalize thrown values into a human-readable string.
 *
 * @param {unknown} err
 * @returns {string}
 */
function getErrorMessage(err) {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return 'Unexpected error.';
}

/**
 * Execute an API call and throw meaningful errors when the request fails.
 *
 * @param {string} endpoint
 * @param {RequestInit} options
 * @returns {Promise<any>}
 */
async function apiCall(endpoint, options) {
  const response = await fetch(endpoint, options);
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const text = await response.text();
    throw new Error(`Unexpected response (${response.status}): ${text}`);
  }
  const data = await response.json();
  if (!response.ok) {
    const message = data?.detail || data?.error || data?.message || 'Request failed.';
    const apiError = new Error(message);
    apiError.status = response.status;
    throw apiError;
  }
  return data;
}

/**
 * Authenticate an account and create an account-scoped session.
 *
 * @param {{username: string, password: string}} params
 * @returns {Promise<any>}
 */
async function login({ username, password }) {
  return apiCall('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
}

/**
 * End an existing session.
 *
 * @param {string} sessionId
 * @returns {Promise<any>}
 */
async function logout(sessionId) {
  return apiCall('/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/**
 * Fetch in-world status. This endpoint requires character selection.
 *
 * @param {string} sessionId
 * @returns {Promise<any>}
 */
async function getStatus(sessionId) {
  return apiCall(`/status/${sessionId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Build the character-list query string.
 *
 * @param {string} sessionId
 * @param {string} worldId
 * @returns {URLSearchParams}
 */
function buildCharacterListParams(sessionId, worldId) {
  return new URLSearchParams({
    session_id: sessionId,
    world_id: worldId,
    // Hide legacy bootstrap characters in the selector when real characters exist.
    exclude_legacy_defaults: 'true',
  });
}

/**
 * Fetch characters available to the session for a specific world.
 *
 * @param {string} sessionId
 * @param {string} worldId
 * @returns {Promise<any>}
 */
async function listCharacters(sessionId, worldId) {
  const params = buildCharacterListParams(sessionId, worldId);
  return apiCall(`/characters?${params.toString()}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Bind a selected character to the active session for gameplay.
 *
 * @param {string} sessionId
 * @param {number} characterId
 * @param {string} worldId
 * @returns {Promise<any>}
 */
async function selectCharacter(sessionId, characterId, worldId) {
  return apiCall('/characters/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      character_id: characterId,
      world_id: worldId,
    }),
  });
}

/**
 * Provision a generated-name character for the active account session.
 *
 * @param {string} sessionId
 * @param {string} worldId
 * @returns {Promise<any>}
 */
async function createCharacter(sessionId, worldId) {
  return apiCall('/characters/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      world_id: worldId,
    }),
  });
}

export {
  apiCall,
  createCharacter,
  getErrorMessage,
  getStatus,
  listCharacters,
  login,
  logout,
  selectCharacter,
};
