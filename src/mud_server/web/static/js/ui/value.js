/*
 * value.js
 *
 * Shared value normalization helpers for admin WebUI rendering.
 */

/**
 * Normalize unknown values into readable text for UI rendering.
 *
 * @param {unknown} value
 * @returns {string}
 */
function formatDisplayValue(value) {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  try {
    return JSON.stringify(value);
  } catch (error) {
    return String(value);
  }
}

export { formatDisplayValue };
