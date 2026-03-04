/*
 * users_render_table.js
 *
 * Table-region render helpers for the admin Users page.
 */

import { escapeHtml, formatRole } from './users_render_shared.js';

function buildOnlineStatus(user) {
  const accountClass = user.is_online_account ? 'is-online' : 'is-offline';
  const worldClass = user.is_online_in_world ? 'is-online' : 'is-offline';
  const activeWorldIds = Array.isArray(user.online_world_ids) ? user.online_world_ids : [];
  const worldChips = activeWorldIds.length
    ? `
      <div class="status-world-list" aria-label="Active worlds">
        ${activeWorldIds
          .map((worldId) => `<span class="status-world-chip">${escapeHtml(worldId)}</span>`)
          .join('')}
      </div>
    `
    : '';
  return `
    <div class="status-stack">
      <span class="badge ${accountClass === 'is-online' ? 'badge--active' : 'badge--muted'}">Account</span>
      <span class="badge ${worldClass === 'is-online' ? 'badge--active' : 'badge--muted'}">
        In-world${activeWorldIds.length ? ` (${activeWorldIds.length})` : ''}
      </span>
      ${worldChips}
    </div>
  `;
}

function buildActionButtons(username) {
  return `
    <div class="actions" data-user-actions="${username}">
      <button class="btn btn--secondary" data-action="change_role">Change role</button>
      <button class="btn btn--secondary" data-action="ban">Ban</button>
      <button class="btn btn--secondary" data-action="unban">Unban</button>
      <button class="btn btn--secondary" data-action="delete">Delete</button>
      <button class="btn btn--secondary" data-action="change_password">Change password</button>
    </div>
  `;
}

function buildSortLabel(label, isActive, direction) {
  if (!isActive) {
    return `${label} <span class="sort-indicator">↕</span>`;
  }
  return `${label} <span class="sort-indicator">${direction === 'asc' ? '▲' : '▼'}</span>`;
}

/**
 * Build the users table HTML, including sortable headers and action buttons.
 *
 * @param {Array<object>} users
 * @param {{key: string, direction: string}} sortState
 * @param {number|null} selectedUserId
 * @returns {string}
 */
function buildUsersTable(users, sortState, selectedUserId) {
  const headers = [
    { label: 'Username', key: 'username' },
    { label: 'Role', key: 'role' },
    { label: 'Online', key: 'online' },
    { label: 'Active', key: 'active' },
    { label: 'Actions', key: null },
  ];

  const headerHtml = headers
    .map((header) => {
      if (!header.key) {
        return '<th>Actions</th>';
      }
      const isActive = sortState.key === header.key;
      const label = buildSortLabel(header.label, isActive, sortState.direction);
      return `<th class="sortable" data-sort-key="${header.key}">${label}</th>`;
    })
    .join('');

  const rowsHtml = users.length
    ? users
        .map((user) => {
          const isSelected = selectedUserId === user.id;
          const rowClass = [
            'is-selectable',
            isSelected ? 'is-selected' : '',
            user.is_online_in_world ? 'is-in-world' : '',
          ]
            .filter(Boolean)
            .join(' ');
          const cells = [
            user.username,
            formatRole(user.role),
            buildOnlineStatus(user),
            user.is_active ? 'Yes' : 'No',
            buildActionButtons(user.username),
          ]
            .map((cell) => `<td>${cell}</td>`)
            .join('');
          return `<tr class="${rowClass}" data-user-id="${user.id}">${cells}</tr>`;
        })
        .join('')
    : `
      <tr>
        <td class="table-empty" colspan="${headers.length}">No users match this filter.</td>
      </tr>
    `;

  return `
    <div class="table-wrap">
      <table class="table">
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

export { buildUsersTable };
