/*
 * login.js
 *
 * Login view for the admin dashboard. Handles authentication using
 * the API client and stores session state locally.
 */

import { Session } from '../api.js';

/**
 * Build the login form markup.
 *
 * @returns {string}
 */
function buildLoginMarkup() {
  return `
    <div class="auth-panel">
      <h1>Admin Login</h1>
      <p class="u-muted">Enter your admin or superuser credentials.</p>
      <form id="login-form" class="detail-form">
        <label>
          Username
          <input class="input" type="text" name="username" required />
        </label>
        <label>
          Password
          <input class="input" type="password" name="password" required />
        </label>
        <button class="btn btn--primary btn--full" type="submit">Sign in</button>
      </form>
      <div id="login-error" class="error" role="alert"></div>
    </div>
  `;
}

/**
 * Render login view into the root element.
 *
 * @param {HTMLElement} root
 * @param {object} api
 */
function renderLogin(root, api) {
  root.innerHTML = `
    <div class="auth-shell">
      ${buildLoginMarkup()}
    </div>
  `;

  const form = root.querySelector('#login-form');
  const error = root.querySelector('#login-error');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.textContent = '';

    const formData = new FormData(form);
    const username = formData.get('username')?.toString().trim() || '';
    const password = formData.get('password')?.toString() || '';

    try {
      const response = await api.login({ username, password });
      Session.write({
        session_id: response.session_id,
        role: response.role,
        available_worlds: response.available_worlds || [],
      });
      window.location.assign('/admin');
    } catch (err) {
      error.textContent = err instanceof Error ? err.message : 'Login failed.';
    }
  });
}

export { renderLogin };
