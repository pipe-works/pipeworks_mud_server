/*
 * users.js
 *
 * Admin users view. Lists users and supports basic management actions.
 */

import { showToast } from '../ui/toasts.js';
import {
  bindCreateCharacterPanel,
  buildCreateCharacterPanel,
} from './users_create_character.js';
import { renderTable } from '../ui/table.js';

function formatRole(role) {
  return role ? role.charAt(0).toUpperCase() + role.slice(1) : 'Unknown';
}

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
      <span class="status-pill ${accountClass}">Account</span>
      <span class="status-pill ${worldClass}">
        In-world${activeWorldIds.length ? ` (${activeWorldIds.length})` : ''}
      </span>
      ${worldChips}
    </div>
  `;
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

/**
 * Build character-management buttons for a character row.
 *
 * Only superusers may remove characters, so lower roles receive no controls.
 */
function buildCharacterActionButtons(characterId, characterName, role, pendingActionKey) {
  if (role !== 'superuser') {
    return '';
  }

  const tombstoneKey = `tombstone:${characterId}`;
  const deleteKey = `delete:${characterId}`;

  return `
    <div class="character-actions">
      <button
        data-character-action="tombstone"
        data-character-id="${characterId}"
        data-character-name="${escapeHtml(characterName)}"
        ${pendingActionKey === tombstoneKey ? 'disabled' : ''}
      >
        ${pendingActionKey === tombstoneKey ? 'Tombstoning...' : 'Tombstone'}
      </button>
      <button
        data-character-action="delete"
        data-character-id="${characterId}"
        data-character-name="${escapeHtml(characterName)}"
        ${pendingActionKey === deleteKey ? 'disabled' : ''}
      >
        ${pendingActionKey === deleteKey ? 'Deleting...' : 'Delete'}
      </button>
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

/**
 * Run a character-management action from the Characters tab.
 */
async function handleCharacterAction({
  api,
  sessionId,
  action,
  characterId,
  characterName,
  refresh,
  setPendingActionKey,
}) {
  const key = `${action}:${characterId}`;
  const actionLabel = action === 'tombstone' ? 'tombstone' : 'permanently delete';
  const warning =
    action === 'tombstone'
      ? `Tombstone character "${characterName}"?`
      : `Permanently delete character "${characterName}"? This cannot be undone.`;
  if (!confirm(warning)) {
    return;
  }

  setPendingActionKey(key);
  try {
    await api.manageCharacter({
      session_id: sessionId,
      character_id: Number(characterId),
      action,
    });
    showToast(`Character "${characterName}" ${actionLabel}d.`, 'success');
    await refresh();
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Character action failed.', 'error');
  } finally {
    setPendingActionKey(null);
  }
}

function buildSortLabel(label, isActive, direction) {
  if (!isActive) {
    return `${label} <span class="sort-indicator">↕</span>`;
  }
  return `${label} <span class="sort-indicator">${direction === 'asc' ? '▲' : '▼'}</span>`;
}

/**
 * Build the users table HTML, including sortable headers and action buttons.
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

/**
 * Sort users based on the active sort state.
 */
function sortUsers(users, sortState) {
  const sorted = [...users];
  const key = sortState.key;
  const direction = sortState.direction === 'asc' ? 1 : -1;

  sorted.sort((a, b) => {
    let aVal = '';
    let bVal = '';
    if (key === 'username') {
      aVal = a.username.toLowerCase();
      bVal = b.username.toLowerCase();
    } else if (key === 'role') {
      aVal = (a.role || '').toLowerCase();
      bVal = (b.role || '').toLowerCase();
    } else if (key === 'active') {
      aVal = a.is_active ? 1 : 0;
      bVal = b.is_active ? 1 : 0;
    } else if (key === 'online') {
      aVal = (a.is_online_account ? 1 : 0) + (a.is_online_in_world ? 1 : 0);
      bVal = (b.is_online_account ? 1 : 0) + (b.is_online_in_world ? 1 : 0);
    }

    if (aVal < bVal) {
      return -1 * direction;
    }
    if (aVal > bVal) {
      return 1 * direction;
    }
    return 0;
  });

  return sorted;
}

function filterUsers(users, searchTerm, activeOnly, onlineOnly) {
  let filtered = [...users];
  if (activeOnly) {
    filtered = filtered.filter((user) => user.is_active);
  }
  if (onlineOnly) {
    filtered = filtered.filter((user) => user.is_online_account || user.is_online_in_world);
  }

  const term = searchTerm.trim().toLowerCase();
  if (!term) {
    return filtered;
  }

  return filtered.filter((user) => {
    const haystack = [user.username, user.role, user.account_origin]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return haystack.includes(term);
  });
}

/**
 * Format optional timestamps for display.
 */
function formatDate(value) {
  if (!value) {
    return '—';
  }
  return `${value}`;
}

function formatAxisScore(score) {
  if (typeof score !== 'number') {
    return '—';
  }
  return score.toFixed(2);
}

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

function buildAxisStatePanel({
  characters,
  axisCharacterId,
  axisState,
  axisEvents,
  isLoading,
  eventsLoading,
  error,
  eventsError,
}) {
  if (!characters.length) {
    return '<p class="muted">No characters available for axis state.</p>';
  }

  const optionsHtml = characters
    .map(
      (character) =>
        `<option value="${character.id}" ${
          Number(character.id) === axisCharacterId ? 'selected' : ''
        }>${escapeHtml(character.name)}</option>`
    )
    .join('');

  if (error) {
    return `
      <div class="axis-state">
        <label class="detail-form axis-state-select">
          Character
          <select data-axis-character>${optionsHtml}</select>
        </label>
        <p class="error">${escapeHtml(error)}</p>
      </div>
    `;
  }

  if (isLoading || !axisState) {
    return `
      <div class="axis-state">
        <label class="detail-form axis-state-select">
          Character
          <select data-axis-character>${optionsHtml}</select>
        </label>
        <p class="muted">Loading axis state...</p>
      </div>
    `;
  }

  const axisRows = axisState.axes?.length
    ? axisState.axes
        .map(
          (axis) => `
            <div>
              <dt>${escapeHtml(axis.axis_name)}</dt>
              <dd>${escapeHtml(axis.axis_label || '—')} (${formatAxisScore(
                axis.axis_score
              )})</dd>
            </div>
          `
        )
        .join('')
    : '<p class="muted">No axis scores recorded.</p>';

  const snapshot =
    axisState.current_state && Object.keys(axisState.current_state).length
      ? JSON.stringify(axisState.current_state, null, 2)
      : null;

  const eventsBody = () => {
    if (eventsError) {
      return `<p class="error">${escapeHtml(eventsError)}</p>`;
    }
    if (eventsLoading) {
      return '<p class="muted">Loading events...</p>';
    }
    if (!axisEvents || axisEvents.length === 0) {
      return '<p class="muted">No axis events recorded.</p>';
    }

    return axisEvents
      .map((event) => {
        const metadata = event.metadata || {};
        const metadataHtml = Object.keys(metadata).length
          ? `
            <div class="tag-list axis-event-tags">
              ${Object.entries(metadata)
                .map(
                  ([key, value]) =>
                    `<span class="tag">${escapeHtml(key)}: ${escapeHtml(value)}</span>`
                )
                .join('')}
            </div>
          `
          : '<p class="muted">No metadata.</p>';

        const deltaHtml = event.deltas
          .map(
            (delta) => `
              <div class="axis-event-delta">
                <span class="axis-event-axis">${escapeHtml(delta.axis_name)}</span>
                <span class="axis-event-values">
                  ${formatAxisScore(delta.old_score)} → ${formatAxisScore(delta.new_score)}
                </span>
                <span class="axis-event-change">${formatAxisScore(delta.delta)}</span>
              </div>
            `
          )
          .join('');

        return `
          <div class="axis-event">
            <div class="axis-event-header">
              <div>
                <div class="axis-event-title">${escapeHtml(event.event_type)}</div>
                <div class="axis-event-sub">${escapeHtml(event.timestamp || '—')}</div>
              </div>
              <div class="axis-event-world">${escapeHtml(event.world_id)}</div>
            </div>
            <div class="axis-event-deltas">${deltaHtml}</div>
            <div class="axis-event-meta">
              ${metadataHtml}
            </div>
          </div>
        `;
      })
      .join('');
  };

  return `
    <div class="axis-state">
      <label class="detail-form axis-state-select">
        Character
        <select data-axis-character>${optionsHtml}</select>
      </label>
      <dl class="detail-list axis-state-summary">
        <div><dt>World</dt><dd>${escapeHtml(axisState.world_id)}</dd></div>
        <div><dt>Seed</dt><dd>${axisState.state_seed ?? '—'}</dd></div>
        <div><dt>Policy</dt><dd>${escapeHtml(axisState.state_version || '—')}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(axisState.state_updated_at || '—')}</dd></div>
      </dl>
      <h5>Axis Scores</h5>
      <dl class="detail-list axis-score-list">${axisRows}</dl>
      <h5>Current Snapshot</h5>
      ${
        snapshot
          ? `<pre class="detail-code">${escapeHtml(snapshot)}</pre>`
          : '<p class="muted">No snapshot data available.</p>'
      }
      <h5>Recent Axis Events</h5>
      <div class="axis-event-list">
        ${eventsBody()}
      </div>
    </div>
  `;
}

/**
 * Build the detail panel for the selected user.
 */
function buildUserDetails({
  user,
  characters,
  worldsById,
  worldOptions,
  permissionsByUser,
  locationsByCharacter,
  sessionRole,
  activeTab,
  createCharacterWorldId,
  createCharacterSubmitting,
  characterActionPending,
  axisState,
  axisCharacterId,
  axisStateLoading,
  axisStateError,
  axisEvents,
  axisEventsLoading,
  axisEventsError,
}) {
  if (!user) {
    return `
      <div class="detail-card tab-card">
        <h3>User Details</h3>
        <p class="muted">Select a user to see account details.</p>
      </div>
    `;
  }

  const userCharacters = characters.filter((character) => character.user_id === user.id);
  const explicitWorldAccess = permissionsByUser.get(user.id) || [];
  // Fallback to character-linked worlds so access is still visible when
  // permissions table rows are absent for legacy/provisioned accounts.
  const inferredWorldAccess = userCharacters
    .map((character) => character.world_id)
    .filter((worldId) => Boolean(worldId));
  const worldAccess = [...new Set([...explicitWorldAccess, ...inferredWorldAccess])];
  const onlineWorldIds = Array.isArray(user.online_world_ids) ? user.online_world_ids : [];
  const onlineWorldNames = onlineWorldIds.map((worldId) => worldsById.get(worldId) || worldId);

  const charactersHtml = userCharacters.length
    ? userCharacters
        .map((character) => {
          const worldName = worldsById.get(character.world_id) || character.world_id;
          const location = locationsByCharacter.get(character.id);
          const room = location?.room_id ? `Room: ${location.room_id}` : 'Room: —';
          const actionButtons = buildCharacterActionButtons(
            character.id,
            character.name,
            sessionRole,
            characterActionPending
          );
          return `
            <div class="detail-row detail-row-character">
              <div>
                <div class="detail-title">${character.name}</div>
                <div class="detail-sub">${worldName}</div>
                <div class="detail-meta">${room}</div>
              </div>
              ${actionButtons}
            </div>
          `;
        })
        .join('')
    : '<p class="muted">No characters found.</p>';

  const worldsHtml = worldAccess.length
    ? worldAccess
        .map((worldId) => {
          const worldName = worldsById.get(worldId) || worldId;
          return `<span class="tag">${worldName}</span>`;
        })
        .join('')
    : '<p class="muted">No world permissions recorded.</p>';

  const tab = activeTab || 'account';

  return `
    <div class="detail-card tab-card users-detail-card" data-user-tabs>
      <div class="tab-header">
        <h3>Account Details</h3>
        <div class="tab-buttons" role="tablist" aria-label="User details tabs">
          <button class="tab-button ${tab === 'account' ? 'is-active' : ''}" data-tab="account">
            Account
          </button>
          <button class="tab-button ${tab === 'characters' ? 'is-active' : ''}" data-tab="characters">
            Characters
          </button>
          <button class="tab-button ${tab === 'worlds' ? 'is-active' : ''}" data-tab="worlds">
            World Access
          </button>
          <button class="tab-button ${tab === 'axis' ? 'is-active' : ''}" data-tab="axis">
            Axis State
          </button>
          <button class="tab-button ${tab === 'create-character' ? 'is-active' : ''}" data-tab="create-character">
            Create Character
          </button>
        </div>
      </div>

      <div class="tab-panel" data-tab-panel="account" ${tab !== 'account' ? 'hidden' : ''}>
        <dl class="detail-list">
          <div><dt>ID</dt><dd>${user.id}</dd></div>
          <div><dt>Username</dt><dd>${user.username}</dd></div>
          <div><dt>Role</dt><dd>${formatRole(user.role)}</dd></div>
          <div><dt>Account Online</dt><dd>${user.is_online_account ? 'Yes' : 'No'}</dd></div>
          <div><dt>In-world</dt><dd>${user.is_online_in_world ? 'Yes' : 'No'}</dd></div>
          <div><dt>In-world Worlds</dt><dd>${onlineWorldNames.join(', ') || '—'}</dd></div>
          <div><dt>Active</dt><dd>${user.is_active ? 'Yes' : 'No'}</dd></div>
          <div><dt>Guest</dt><dd>${user.is_guest ? 'Yes' : 'No'}</dd></div>
          <div><dt>Origin</dt><dd>${user.account_origin || '—'}</dd></div>
          <div><dt>Created</dt><dd>${formatDate(user.created_at)}</dd></div>
          <div><dt>Last Login</dt><dd>${formatDate(user.last_login)}</dd></div>
          <div><dt>Guest Expires</dt><dd>${formatDate(user.guest_expires_at)}</dd></div>
          <div><dt>Tombstoned</dt><dd>${formatDate(user.tombstoned_at)}</dd></div>
          <div><dt>Characters</dt><dd>${user.character_count ?? 0}</dd></div>
        </dl>
      </div>

      <div class="tab-panel" data-tab-panel="characters" ${tab !== 'characters' ? 'hidden' : ''}>
        <h4>Characters</h4>
        ${
          sessionRole === 'superuser'
            ? '<p class="muted detail-help">Superusers may tombstone or permanently delete characters.</p>'
            : ''
        }
        ${charactersHtml}
      </div>

      <div class="tab-panel" data-tab-panel="worlds" ${tab !== 'worlds' ? 'hidden' : ''}>
        <h4>World Access</h4>
        <div class="tag-list">${worldsHtml}</div>
      </div>

      <div class="tab-panel" data-tab-panel="axis" ${tab !== 'axis' ? 'hidden' : ''}>
        <h4>Axis State</h4>
        ${buildAxisStatePanel({
          characters: userCharacters,
          axisCharacterId,
          axisState,
          axisEvents,
          isLoading: axisStateLoading,
          eventsLoading: axisEventsLoading,
          error: axisStateError,
          eventsError: axisEventsError,
        })}
      </div>

      <div class="tab-panel" data-tab-panel="create-character" ${tab !== 'create-character' ? 'hidden' : ''}>
        <h4>Create Character</h4>
        ${buildCreateCharacterPanel({
          user,
          worlds: worldOptions,
          selectedWorldId: createCharacterWorldId,
          isSubmitting: createCharacterSubmitting,
        })}
      </div>
    </div>
  `;
}

/**
 * Build the create-account form with role-based options.
 */
function buildCreateUserCard(role) {
  const roleOptions =
    role === 'superuser'
      ? ['player', 'worldbuilder', 'admin', 'superuser']
      : ['player', 'worldbuilder'];

  return `
    <div class="detail-card users-create-card">
      <h3>Create Account</h3>
      <form class="detail-form" data-create-user>
        <label>
          Username
          <input type="text" name="username" required />
        </label>
        <label>
          Role
          <select name="role">
            ${roleOptions.map((opt) => `<option value="${opt}">${opt}</option>`).join('')}
          </select>
        </label>
        <label>
          Password
          <input type="password" name="password" required />
        </label>
        <label>
          Confirm Password
          <input type="password" name="password_confirm" required />
        </label>
        <button type="submit">Create account</button>
      </form>
      <p class="muted detail-help">Admins can create players/worldbuilders. Superusers can create all roles.</p>
    </div>
  `;
}

function isTombstonedCharacter(character) {
  const hasDetachedOwner = character.user_id === null || character.user_id === undefined;
  const isTombstoneName =
    typeof character.name === 'string' && character.name.startsWith('tombstone_');
  return hasDetachedOwner && isTombstoneName;
}

/**
 * Build a compact table of tombstoned characters for admin auditing.
 */
function buildTombstonedCharactersCard(characters, worldsById) {
  const tombstoned = characters
    .filter((character) => isTombstonedCharacter(character))
    .sort((a, b) => {
      const aTs = Date.parse(a.updated_at || a.created_at || '') || 0;
      const bTs = Date.parse(b.updated_at || b.created_at || '') || 0;
      return bTs - aTs;
    })
    .slice(0, 50);

  if (!tombstoned.length) {
    return `
      <div class="detail-card users-tombstoned-card">
        <h3>Tombstoned Characters</h3>
        <p class="muted">No tombstoned characters recorded.</p>
      </div>
    `;
  }

  const headers = ['ID', 'Character', 'World', 'Updated'];
  const rows = tombstoned.map((character) => {
    const worldName = worldsById.get(character.world_id) || character.world_id || '—';
    return [
      `${character.id ?? '—'}`,
      escapeHtml(character.name || '—'),
      escapeHtml(worldName),
      escapeHtml(formatDate(character.updated_at || character.created_at)),
    ];
  });

  return `
    <div class="detail-card users-tombstoned-card">
      <h3>Tombstoned Characters</h3>
      <p class="muted">Most recent tombstoned character records for audit/recovery workflows.</p>
      ${renderTable(headers, rows)}
    </div>
  `;
}

/**
 * Build the persistent users page shell.
 *
 * Important UX behavior:
 * - The create-account card is rendered once and kept mounted.
 * - Auto-refresh updates only the users table + detail panel regions.
 * - This avoids form resets and focus jumps while admins are typing.
 */
function buildUsersPageShell(role) {
  return `
    <div class="page">
      <div class="page-header">
        <div>
          <h2>Users</h2>
          <p class="muted" data-users-count>Loading users...</p>
        </div>
      </div>
      <div class="split-layout users-split">
        <div class="users-left">
          <div data-users-table-region></div>
          <div class="users-bottom-row">
            ${buildCreateUserCard(role)}
            <div data-users-secondary-region></div>
          </div>
        </div>
        <aside class="detail-panel" data-users-detail-region></aside>
      </div>
    </div>
  `;
}

/**
 * Convert tabular rows (column list + row arrays) into objects.
 */
function rowsToObjects(columns, rows) {
  return rows.map((row) => {
    const record = {};
    columns.forEach((col, idx) => {
      record[col] = row[idx];
    });
    return record;
  });
}

async function renderUsers(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Users</h1>
      <p class="muted">Loading users...</p>
    </div>
  `;

  const sessionId = session.session_id;
  // -----------------------------------------------------------------------
  // Local view state (preserved across refreshes)
  // -----------------------------------------------------------------------
  const AUTO_REFRESH_INTERVAL_MS = 15000;
  const sortState = { key: 'username', direction: 'asc' };
  let selectedUserId = null;
  let searchTerm = '';
  let activeOnly = false;
  let onlineOnly = false;
  let activeDetailTab = 'account';
  let createCharacterWorldId = '';
  let createCharacterSubmitting = false;
  let characterActionPending = null;
  let activeAxisCharacterId = null;
  let axisStateError = null;
  let axisEventsError = null;

  let users = [];
  let characters = [];
  let worldsById = new Map();
  let permissionsByUser = new Map();
  let locationsByCharacter = new Map();
  let metadataLoaded = false;
  let lastRefreshAt = null;
  let autoRefreshHandle = null;
  let refreshPromise = null;

  const axisStateCache = new Map();
  const axisStateLoading = new Set();
  const axisEventsCache = new Map();
  const axisEventsLoading = new Set();

  // Render a stable layout once so auto-refresh updates only data regions.
  root.innerHTML = buildUsersPageShell(session.role);
  const tableRegion = root.querySelector('[data-users-table-region]');
  const secondaryRegion = root.querySelector('[data-users-secondary-region]');
  const detailRegion = root.querySelector('[data-users-detail-region]');
  const usersCountLabel = root.querySelector('[data-users-count]');
  const createForm = root.querySelector('[data-create-user]');
  if (!tableRegion || !secondaryRegion || !detailRegion || !usersCountLabel || !createForm) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Users</h1>
        <p class="error">Failed to render users UI shell.</p>
      </div>
    `;
    return;
  }

  // Bind once: this form should remain mounted between table refreshes.
  createForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(createForm);
    const payload = {
      session_id: sessionId,
      username: (formData.get('username') || '').toString().trim(),
      role: (formData.get('role') || '').toString(),
      password: (formData.get('password') || '').toString(),
      password_confirm: (formData.get('password_confirm') || '').toString(),
    };

    try {
      await api.createUser(payload);
      showToast(`Created user '${payload.username}'.`, 'success');
      createForm.reset();
      await refreshData({ includeMetadata: true, showErrorToast: false });
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to create user.', 'error');
    }
  });

  /**
   * Build human-readable sync text for the auto-refresh hint.
   */
  const getRefreshHint = () => {
    if (!lastRefreshAt) {
      return 'Auto refresh every 15s · waiting for first sync';
    }
    return `Auto refresh every 15s · last sync ${lastRefreshAt.toLocaleTimeString()}`;
  };

  /**
   * Pull the main users list.
   *
   * This is the lightest refresh path and is used by the auto-refresh timer.
   */
  const loadUsersOnly = async () => {
    const response = await api.getPlayers(sessionId);
    users = Array.isArray(response.players) ? response.players : [];
    lastRefreshAt = new Date();
  };

  /**
   * Pull metadata tables needed for the right-side details panel.
   */
  const loadMetadata = async ({ showErrorToast = true } = {}) => {
    try {
      const [charactersResp, worldsResp, permissionsResp, locationsResp] = await Promise.all([
        api.getTableRows(sessionId, 'characters', 1000),
        api.getTableRows(sessionId, 'worlds', 200),
        api.getTableRows(sessionId, 'world_permissions', 1000),
        api.getTableRows(sessionId, 'character_locations', 1000),
      ]);

      const worldRows = rowsToObjects(worldsResp.columns, worldsResp.rows);
      worldsById = new Map(worldRows.map((world) => [world.id, world.name]));

      characters = rowsToObjects(charactersResp.columns, charactersResp.rows);
      const permissions = rowsToObjects(permissionsResp.columns, permissionsResp.rows);
      const locations = rowsToObjects(locationsResp.columns, locationsResp.rows);

      permissionsByUser = new Map();
      permissions
        .filter((entry) => entry.can_access)
        .forEach((entry) => {
          const existing = permissionsByUser.get(entry.user_id) || [];
          existing.push(entry.world_id);
          permissionsByUser.set(entry.user_id, existing);
        });

      locationsByCharacter = new Map(
        locations.map((location) => [location.character_id, location])
      );
      metadataLoaded = true;
    } catch (err) {
      if (showErrorToast) {
        showToast('Unable to load character/world metadata.', 'error');
      }
    }
  };

  /**
   * Refresh page data and optionally metadata, then re-render the view.
   *
   * A guard avoids overlapping refresh requests when auto-refresh and user
   * actions happen close together.
   */
  const refreshData = async ({ includeMetadata = false, showErrorToast = true } = {}) => {
    if (refreshPromise) {
      await refreshPromise;
      if (!includeMetadata || metadataLoaded) {
        return;
      }
    }

    refreshPromise = (async () => {
      await loadUsersOnly();
      if (includeMetadata || !metadataLoaded) {
        await loadMetadata({ showErrorToast });
      }
      renderPage();
    })();

    try {
      await refreshPromise;
    } finally {
      refreshPromise = null;
    }
  };

  /**
   * Ensure axis snapshot data for a selected character exists in the local cache.
   */
  const ensureAxisState = async (characterId) => {
    if (!characterId || axisStateCache.has(characterId) || axisStateLoading.has(characterId)) {
      return;
    }

    axisStateLoading.add(characterId);
    axisStateError = null;

    try {
      const response = await api.getCharacterAxisState(sessionId, characterId);
      axisStateCache.set(characterId, response);
    } catch (err) {
      axisStateError = err instanceof Error ? err.message : 'Unable to load axis state.';
    } finally {
      axisStateLoading.delete(characterId);
      renderPage();
    }
  };

  /**
   * Ensure axis event history for a selected character exists in the local cache.
   */
  const ensureAxisEvents = async (characterId) => {
    if (!characterId || axisEventsCache.has(characterId) || axisEventsLoading.has(characterId)) {
      return;
    }

    axisEventsLoading.add(characterId);
    axisEventsError = null;

    try {
      const response = await api.getCharacterAxisEvents(sessionId, characterId, 25);
      axisEventsCache.set(characterId, response.events || []);
    } catch (err) {
      axisEventsError = err instanceof Error ? err.message : 'Unable to load axis events.';
    } finally {
      axisEventsLoading.delete(characterId);
      renderPage();
    }
  };

  /**
   * Render mutable regions for table/details from local state.
   */
  const renderPage = () => {
    const activeElement = document.activeElement;
    const searchWasFocused =
      activeElement instanceof HTMLInputElement && activeElement.id === 'user-search';
    const selectionStart = searchWasFocused ? activeElement.selectionStart : null;
    const selectionEnd = searchWasFocused ? activeElement.selectionEnd : null;
    const previousScrollTop = tableRegion.querySelector('.table-wrap')?.scrollTop ?? null;
    const previousDetailScrollByTab = {};
    detailRegion.querySelectorAll('.users-detail-card .tab-panel[data-tab-panel]').forEach((panel) => {
      const tabName = panel.getAttribute('data-tab-panel');
      if (!tabName) {
        return;
      }
      // Preserve per-tab vertical scroll positions so auto-refresh does not
      // force readers back to the top of long panes like Axis State.
      previousDetailScrollByTab[tabName] = panel.scrollTop;
    });

    const filteredUsers = filterUsers(users, searchTerm, activeOnly, onlineOnly);
    const sortedUsers = sortUsers(filteredUsers, sortState);
    if (sortedUsers.length === 0) {
      selectedUserId = null;
    } else if (!selectedUserId || !sortedUsers.some((user) => user.id === selectedUserId)) {
      selectedUserId = sortedUsers[0].id;
    }
    const selectedUser =
      sortedUsers.find((user) => user.id === selectedUserId) || sortedUsers[0] || null;
    const worldOptions = Array.from(worldsById.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.id.localeCompare(b.id));
    const availableWorldIds = new Set(worldOptions.map((world) => world.id));
    if (!createCharacterWorldId || !availableWorldIds.has(createCharacterWorldId)) {
      createCharacterWorldId = worldOptions[0]?.id || '';
    }
    const selectedCharacters = characters.filter((character) => character.user_id === selectedUser?.id);
    const axisCharacterIds = selectedCharacters.map((character) => Number(character.id));
    if (!axisCharacterIds.includes(activeAxisCharacterId)) {
      activeAxisCharacterId = axisCharacterIds[0] ?? null;
      axisStateError = null;
      axisEventsError = null;
    }
    const axisState = activeAxisCharacterId !== null ? axisStateCache.get(activeAxisCharacterId) : null;
    const axisStateLoadingActive =
      activeAxisCharacterId !== null && axisStateLoading.has(activeAxisCharacterId);
    const axisEvents = activeAxisCharacterId !== null ? axisEventsCache.get(activeAxisCharacterId) : null;
    const axisEventsLoadingActive =
      activeAxisCharacterId !== null && axisEventsLoading.has(activeAxisCharacterId);

    usersCountLabel.textContent = `${sortedUsers.length} of ${users.length} users shown.`;

    tableRegion.innerHTML = `
      <div class="card table-card users-table-card">
        <h3>Active Users</h3>
        <div class="table-toolbar">
          <label class="table-search">
            <span>Search</span>
            <input
              type="search"
              id="user-search"
              placeholder="Username, role, origin"
              value="${searchTerm.replace(/"/g, '&quot;')}"
            />
          </label>
          <label class="table-toggle">
            <input type="checkbox" id="user-active-only" ${activeOnly ? 'checked' : ''} />
            <span>Active only</span>
          </label>
          <label class="table-toggle">
            <input type="checkbox" id="user-online-only" ${onlineOnly ? 'checked' : ''} />
            <span>Online only</span>
          </label>
          <span class="table-refresh-note">${getRefreshHint()}</span>
        </div>
        ${buildUsersTable(sortedUsers, sortState, selectedUser?.id)}
      </div>
    `;
    secondaryRegion.innerHTML = buildTombstonedCharactersCard(characters, worldsById);

    detailRegion.innerHTML = `
      ${buildUserDetails({
        user: selectedUser,
        characters,
        worldsById,
        worldOptions,
        permissionsByUser,
        locationsByCharacter,
        sessionRole: session.role,
        activeTab: activeDetailTab,
        createCharacterWorldId,
        createCharacterSubmitting,
        characterActionPending,
        axisState,
        axisCharacterId: activeAxisCharacterId,
        axisStateLoading: axisStateLoadingActive,
        axisStateError,
        axisEvents,
        axisEventsLoading: axisEventsLoadingActive,
        axisEventsError,
      })}
    `;

    tableRegion.querySelectorAll('[data-user-actions]').forEach((container) => {
      const username = container.getAttribute('data-user-actions');
      container.querySelectorAll('button').forEach((button) => {
        button.addEventListener('click', (event) => {
          event.stopPropagation();
          handleAction({
            api,
            sessionId,
            action: button.dataset.action,
            username,
            refresh: async () => refreshData({ includeMetadata: false, showErrorToast: false }),
          });
        });
      });
    });

    tableRegion.querySelectorAll('th.sortable').forEach((header) => {
      header.addEventListener('click', () => {
        const key = header.dataset.sortKey;
        if (!key) {
          return;
        }
        if (sortState.key === key) {
          sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
        } else {
          sortState.key = key;
          sortState.direction = 'asc';
        }
        renderPage();
      });
    });

    tableRegion.querySelectorAll('tr[data-user-id]').forEach((row) => {
      row.addEventListener('click', () => {
        selectedUserId = Number(row.dataset.userId);
        renderPage();
      });
    });

    detailRegion.querySelectorAll('.tab-button[data-tab]').forEach((button) => {
      button.addEventListener('click', () => {
        activeDetailTab = button.dataset.tab;
        renderPage();
      });
    });

    detailRegion.querySelectorAll('[data-character-action]').forEach((button) => {
      button.addEventListener('click', async (event) => {
        event.stopPropagation();
        const action = button.getAttribute('data-character-action');
        const characterId = button.getAttribute('data-character-id');
        const characterName = button.getAttribute('data-character-name') || 'character';
        if (!action || !characterId) {
          return;
        }
        await handleCharacterAction({
          api,
          sessionId,
          action,
          characterId,
          characterName,
          refresh: async () => refreshData({ includeMetadata: true, showErrorToast: false }),
          setPendingActionKey: (value) => {
            characterActionPending = value;
            renderPage();
          },
        });
      });
    });

    bindCreateCharacterPanel({
      root: detailRegion,
      api,
      sessionId,
      user: selectedUser,
      selectedWorldId: createCharacterWorldId,
      setSelectedWorldId: (value) => {
        createCharacterWorldId = value;
      },
      setIsSubmitting: (value) => {
        createCharacterSubmitting = value;
        renderPage();
      },
      onSuccess: async (response) => {
        const createdName = response?.character_name || 'character';
        const createdSeed = response?.seed ? ` (seed ${response.seed})` : '';
        showToast(`Created ${createdName}${createdSeed}.`, 'success');
        if (response?.entity_state_error) {
          showToast(response.entity_state_error, 'error');
        }
        await refreshData({ includeMetadata: true, showErrorToast: false });
      },
      onError: (error) => {
        showToast(error instanceof Error ? error.message : 'Failed to create character.', 'error');
      },
    });

    const axisSelect = detailRegion.querySelector('[data-axis-character]');
    if (axisSelect) {
      axisSelect.addEventListener('change', (event) => {
        activeAxisCharacterId = Number(event.target.value);
        axisStateError = null;
        axisEventsError = null;
        renderPage();
      });
    }

    const searchInput = tableRegion.querySelector('#user-search');
    if (searchInput) {
      searchInput.addEventListener('input', (event) => {
        searchTerm = event.target.value;
        renderPage();
      });
    }

    const activeToggle = tableRegion.querySelector('#user-active-only');
    if (activeToggle) {
      activeToggle.addEventListener('change', (event) => {
        activeOnly = event.target.checked;
        renderPage();
      });
    }

    const onlineToggle = tableRegion.querySelector('#user-online-only');
    if (onlineToggle) {
      onlineToggle.addEventListener('change', (event) => {
        onlineOnly = event.target.checked;
        renderPage();
      });
    }

    if (searchInput && searchWasFocused) {
      searchInput.focus();
      if (selectionStart !== null && selectionEnd !== null) {
        searchInput.setSelectionRange(selectionStart, selectionEnd);
      }
    }

    if (previousScrollTop !== null) {
      const tableWrap = tableRegion.querySelector('.table-wrap');
      if (tableWrap) {
        tableWrap.scrollTop = previousScrollTop;
      }
    }

    Object.entries(previousDetailScrollByTab).forEach(([tabName, scrollTop]) => {
      const panel = detailRegion.querySelector(
        `.users-detail-card .tab-panel[data-tab-panel="${tabName}"]`
      );
      if (panel) {
        panel.scrollTop = scrollTop;
      }
    });

    if (activeDetailTab === 'axis' && activeAxisCharacterId) {
      ensureAxisState(activeAxisCharacterId);
      ensureAxisEvents(activeAxisCharacterId);
    }
  };

  /**
   * Start periodic users-table refresh.
   */
  const startAutoRefresh = () => {
    if (autoRefreshHandle) {
      clearInterval(autoRefreshHandle);
    }
    autoRefreshHandle = window.setInterval(async () => {
      if (!root.isConnected) {
        clearInterval(autoRefreshHandle);
        autoRefreshHandle = null;
        return;
      }
      if (document.hidden) {
        return;
      }
      try {
        await refreshData({ includeMetadata: false, showErrorToast: false });
      } catch (_err) {
        // Keep auto-refresh quiet; user-driven actions surface actionable errors.
      }
    }, AUTO_REFRESH_INTERVAL_MS);
  };

  try {
    await refreshData({ includeMetadata: true, showErrorToast: true });
    startAutoRefresh();
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
