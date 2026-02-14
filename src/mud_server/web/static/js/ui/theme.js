/*
 * theme.js
 *
 * Handles light/dark theme persistence and toggling.
 */

const THEME_KEY = 'mud_admin_theme';

function getStoredTheme() {
  return localStorage.getItem(THEME_KEY);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
}

function initThemeToggle({ button }) {
  const stored = getStoredTheme();
  if (stored) {
    applyTheme(stored);
  }

  if (!button) {
    return;
  }

  button.addEventListener('click', () => {
    const current = document.documentElement.dataset.theme || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  });
}

export { initThemeToggle };
