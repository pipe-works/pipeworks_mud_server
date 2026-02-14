/*
 * app.js
 *
 * Entry point for the admin WebUI. Handles session checks and basic routing.
 */

import { ApiClient, Session } from './api.js';
import { renderLogin } from './pages/login.js';
import { renderDashboard } from './pages/dashboard.js';

const api = new ApiClient();

/**
 * Ensure the current session exists and has admin privileges.
 *
 * @returns {{session: object|null, isAuthorized: boolean}}
 */
function getSessionState() {
  const session = Session.read();
  const role = session?.role || '';
  const isAuthorized = role === 'admin' || role === 'superuser';
  return { session, isAuthorized };
}

/**
 * Render the appropriate view based on session state.
 */
function render() {
  const root = document.getElementById('app');
  if (!root) {
    return;
  }

  const { session, isAuthorized } = getSessionState();

  if (!session || !isAuthorized) {
    renderLogin(root, api);
    return;
  }

  renderDashboard(root, session);
}

render();
