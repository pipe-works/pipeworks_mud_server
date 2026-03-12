/*
 * app.js
 *
 * Entry point for the admin WebUI. Handles session checks, routing, and layout.
 */

import { ApiClient, Session } from './api.js';
import { renderLogin } from './pages/login.js';
import { renderDashboard } from './pages/dashboard.js';
import { renderUsers } from './pages/users.js';
import { renderAccountsDashboard } from './pages/accounts.js';
import { renderCharactersDashboard } from './pages/characters.js';
import { renderTombstonesDashboard } from './pages/tombstones.js';
import { renderSessions } from './pages/sessions.js';
import { renderConnections } from './pages/connections.js';
import { renderLocations } from './pages/locations.js';
import { renderChat } from './pages/chat.js';
import { renderTables } from './pages/tables.js';
import { renderWorlds } from './pages/worlds.js';
import { renderSuperuser } from './pages/superuser.js';
import { renderSchema } from './pages/schema.js';
import { renderNav } from './ui/nav.js';
import { initThemeToggle } from './ui/theme.js';

const api = new ApiClient();

const ROUTES = {
  '/admin': renderDashboard,
  '/admin/': renderDashboard,
  '/admin/users': renderUsers,
  '/admin/accounts': renderAccountsDashboard,
  '/admin/characters': renderCharactersDashboard,
  '/admin/tombstones': renderTombstonesDashboard,
  '/admin/sessions': renderSessions,
  '/admin/connections': renderConnections,
  '/admin/locations': renderLocations,
  '/admin/chat': renderChat,
  '/admin/tables': renderTables,
  '/admin/schema': renderSchema,
  '/admin/worlds': renderWorlds,
  '/admin/superuser': renderSuperuser,
};

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

function buildShell({ appVersion }) {
  return `
    <header class="app-header">
      <span class="app-header__title">🛠 Mud Server Admin</span>
      <span class="app-header__subtitle">Pipe-Works · Admin Control Surface · v${appVersion}</span>
      <button
        id="theme-toggle"
        class="theme-toggle"
        type="button"
        data-theme-toggle
        aria-label="Toggle dark and light theme"
      >☀ Light</button>
      <button class="btn btn--secondary btn--sm" type="button" data-logout>Logout</button>
    </header>
    <div class="layout">
      <aside class="sidebar">
        <div class="brand">PipeWorks Admin</div>
        <nav class="nav" data-nav></nav>
      </aside>
      <main class="main">
        <section class="content" data-content></section>
      </main>
    </div>
  `;
}

function handleLogout(session) {
  if (!session?.session_id) {
    Session.clear();
    window.location.assign('/admin');
    return;
  }

  api.logout(session.session_id).finally(() => {
    Session.clear();
    window.location.assign('/admin');
  });
}

/**
 * Render the appropriate view based on session state and route.
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

  const appVersion = document.body?.dataset?.appVersion?.trim() || '0.0.0-dev';
  root.innerHTML = buildShell({ appVersion });

  const content = root.querySelector('[data-content]');
  const activePath = window.location.pathname;
  const view = ROUTES[activePath] || renderDashboard;

  renderNav({ root, activePath, role: session.role });

  const themeButton = root.querySelector('[data-theme-toggle]');
  initThemeToggle({ button: themeButton });

  const logoutButton = root.querySelector('[data-logout]');
  logoutButton.addEventListener('click', () => handleLogout(session));

  view(content, { api, session });
}

render();
