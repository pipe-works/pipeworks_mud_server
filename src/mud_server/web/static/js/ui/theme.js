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

function updateThemeButton(button, theme) {
  if (!button) {
    return;
  }
  const nextTheme = theme === 'light' ? 'dark' : 'light';
  button.textContent = nextTheme === 'light' ? '\u2600 Light' : '\u263E Dark';
  button.title = `Switch to ${nextTheme} theme`;
}

function initThemeToggle({ button }) {
  const stored = getStoredTheme();
  const currentTheme = stored || document.documentElement.dataset.theme || 'dark';
  applyTheme(currentTheme);
  updateThemeButton(button, currentTheme);

  if (!button) {
    return;
  }

  button.addEventListener('click', () => {
    const current = document.documentElement.dataset.theme || 'dark';
    const next = current === 'light' ? 'dark' : 'light';
    applyTheme(next);
    updateThemeButton(button, next);
  });
}

export { initThemeToggle };
