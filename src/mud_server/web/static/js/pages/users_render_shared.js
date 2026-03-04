/*
 * users_render_shared.js
 *
 * Shared formatting helpers for admin Users page render modules.
 */

/**
 * Escape plain text for safe HTML insertion.
 *
 * @param {unknown} value
 * @returns {string}
 */
function escapeHtml(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Format roles for display.
 *
 * @param {string|null|undefined} role
 * @returns {string}
 */
function formatRole(role) {
  return role ? role.charAt(0).toUpperCase() + role.slice(1) : 'Unknown';
}

/**
 * Format optional timestamps for display.
 *
 * @param {unknown} value
 * @returns {string}
 */
function formatDate(value) {
  if (!value) {
    return '—';
  }
  return `${value}`;
}

export { escapeHtml, formatDate, formatRole };
