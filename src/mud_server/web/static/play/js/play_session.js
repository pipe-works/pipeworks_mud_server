/*
 * play_session.js
 *
 * Session and flash-message storage helpers for the play shell.
 */

const STORAGE_KEY = 'pipeworks_play_session';
const FLASH_KEY = 'pipeworks_play_flash';

/**
 * Read account/character session payload from sessionStorage.
 *
 * @returns {Record<string, unknown>|null}
 */
function readSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_err) {
    return null;
  }
}

/**
 * Persist session payload for play shell flows.
 *
 * @param {Record<string, unknown>} payload
 * @returns {void}
 */
function writeSession(payload) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

/**
 * Merge session patch data into the existing payload.
 *
 * @param {Record<string, unknown>} patch
 * @returns {void}
 */
function updateSession(patch) {
  const current = readSession() || {};
  writeSession({ ...current, ...patch });
}

/**
 * Remove current session payload.
 *
 * @returns {void}
 */
function clearSession() {
  sessionStorage.removeItem(STORAGE_KEY);
}

/**
 * Persist a one-time flash message to show after navigation.
 *
 * @param {string} message
 * @returns {void}
 */
function writeFlashMessage(message) {
  sessionStorage.setItem(FLASH_KEY, message);
}

/**
 * Read and remove a one-time flash message.
 *
 * @returns {string}
 */
function consumeFlashMessage() {
  const message = sessionStorage.getItem(FLASH_KEY) || '';
  if (message) {
    sessionStorage.removeItem(FLASH_KEY);
  }
  return message;
}

export {
  clearSession,
  consumeFlashMessage,
  readSession,
  updateSession,
  writeFlashMessage,
  writeSession,
};
