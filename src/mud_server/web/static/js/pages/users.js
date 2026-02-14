/*
 * users.js
 *
 * Admin users view. Lists users and supports basic management actions.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

function formatRole(role) {
  return role ? role.charAt(0).toUpperCase() + role.slice(1) : 'Unknown';
}

function buildActionButtons(username) {
  return `
    <div class="actions" data-user-actions="${username}">
      <button data-action="change_role">Change role</button>
      <button data-action="ban">Ban</button>
      <button data-action="unban">Unban</button>
      <button data-action="delete">Delete</button>
      <button data-action="change_password">Change password</button>
    </div>
  `;
}

async function handleAction({ api, sessionId, action, username, refresh }) {
  let payload = {
    session_id: sessionId,
    action,
    target_username: username,
  };

  if (action === 'change_role') {
    const newRole = prompt('Enter new role (player, worldbuilder, admin, superuser):');
    if (!newRole) {
      return;
    }
    payload = { ...payload, new_role: newRole.trim().toLowerCase() };
  }

  if (action === 'change_password') {
    const newPassword = prompt('Enter new password (min 8 chars):');
    if (!newPassword) {
      return;
    }
    payload = { ...payload, new_password: newPassword };
  }

  if (action === 'delete') {
    const confirmed = confirm(`Delete user ${username}? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
  }

  try {
    await api.manageUser(payload);
    showToast(`Action '${action}' completed.`, 'success');
    await refresh();
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Action failed.', 'error');
  }
}

async function renderUsers(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Users</h1>
      <p class="muted">Loading users...</p>
    </div>
  `;

  const sessionId = session.session_id;

  async function load() {
    const response = await api.getPlayers(sessionId);
    const headers = ['Username', 'Role', 'Active', 'Actions'];
    const rows = response.players.map((user) => [
      user.username,
      formatRole(user.role),
      user.is_active ? 'Yes' : 'No',
      buildActionButtons(user.username),
    ]);

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Users</h2>
            <p class="muted">${rows.length} users found.</p>
          </div>
        </div>
        <div class="card table-card">
          ${renderTable(headers, rows)}
        </div>
      </div>
    `;

    root.querySelectorAll('[data-user-actions]').forEach((container) => {
      const username = container.getAttribute('data-user-actions');
      container.querySelectorAll('button').forEach((button) => {
        button.addEventListener('click', () => {
          handleAction({
            api,
            sessionId,
            action: button.dataset.action,
            username,
            refresh: load,
          });
        });
      });
    });
  }

  try {
    await load();
  } catch (err) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Users</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load users.'}</p>
      </div>
    `;
  }
}

export { renderUsers };
