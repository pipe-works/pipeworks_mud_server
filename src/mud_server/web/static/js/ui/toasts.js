/*
 * toasts.js
 *
 * Simple toast notification system.
 */

const DEFAULT_TIMEOUT = 4000;

/**
 * Ensure the toast container exists.
 *
 * @returns {HTMLElement}
 */
function getContainer() {
  let container = document.querySelector('[data-toast-container]');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    container.dataset.toastContainer = 'true';
    document.body.appendChild(container);
  }
  return container;
}

/**
 * Show a toast message.
 *
 * @param {string} message
 * @param {string} type
 * @param {number} timeout
 */
function showToast(message, type = 'info', timeout = DEFAULT_TIMEOUT) {
  const container = getContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-hide');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  }, timeout);
}

export { showToast };
