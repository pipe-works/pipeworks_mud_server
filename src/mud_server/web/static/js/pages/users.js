/*
 * users.js
 *
 * Admin users view. Lists users and supports basic management actions.
 */

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
          const rowClass = isSelected ? 'is-selected is-selectable' : 'is-selectable';
          const cells = [
            user.username,
            formatRole(user.role),
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

function filterUsers(users, searchTerm, activeOnly) {
  let filtered = [...users];
  if (activeOnly) {
    filtered = filtered.filter((user) => user.is_active);
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
  isLoading,
  error,
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
  permissionsByUser,
  locationsByCharacter,
  activeTab,
  axisState,
  axisCharacterId,
  axisStateLoading,
  axisStateError,
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
  const worldAccess = permissionsByUser.get(user.id) || [];

  const charactersHtml = userCharacters.length
    ? userCharacters
        .map((character) => {
          const worldName = worldsById.get(character.world_id) || character.world_id;
          const location = locationsByCharacter.get(character.id);
          const room = location?.room_id ? `Room: ${location.room_id}` : 'Room: —';
          return `
            <div class="detail-row">
              <div>
                <div class="detail-title">${character.name}</div>
                <div class="detail-sub">${worldName}</div>
              </div>
              <div class="detail-meta">${room}</div>
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
        </div>
      </div>

      <div class="tab-panel" data-tab-panel="account" ${tab !== 'account' ? 'hidden' : ''}>
        <dl class="detail-list">
          <div><dt>ID</dt><dd>${user.id}</dd></div>
          <div><dt>Username</dt><dd>${user.username}</dd></div>
          <div><dt>Role</dt><dd>${formatRole(user.role)}</dd></div>
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
          isLoading: axisStateLoading,
          error: axisStateError,
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

  async function load() {
    const response = await api.getPlayers(sessionId);
    const users = response.players;
    const sortState = { key: 'username', direction: 'asc' };
    let selectedUserId = users[0]?.id ?? null;
    let searchTerm = '';
    let activeOnly = false;
    let activeDetailTab = 'account';
    let activeAxisCharacterId = null;
    let axisStateError = null;

    let characters = [];
    let worldsById = new Map();
    let permissionsByUser = new Map();
    let locationsByCharacter = new Map();
    const axisStateCache = new Map();
    const axisStateLoading = new Set();

    try {
      const [charactersResp, worldsResp, permissionsResp, locationsResp] =
        await Promise.all([
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
    } catch (err) {
      showToast('Unable to load character/world metadata.', 'error');
    }

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

    const renderPage = () => {
      const activeElement = document.activeElement;
      const searchWasFocused =
        activeElement instanceof HTMLInputElement && activeElement.id === 'user-search';
      const selectionStart = searchWasFocused ? activeElement.selectionStart : null;
      const selectionEnd = searchWasFocused ? activeElement.selectionEnd : null;
      const previousScrollTop = root.querySelector('.table-wrap')?.scrollTop ?? null;

      const filteredUsers = filterUsers(users, searchTerm, activeOnly);
      const sortedUsers = sortUsers(filteredUsers, sortState);
      if (sortedUsers.length === 0) {
        selectedUserId = null;
      } else if (!selectedUserId || !sortedUsers.some((user) => user.id === selectedUserId)) {
        selectedUserId = sortedUsers[0].id;
      }
      const selectedUser =
        sortedUsers.find((user) => user.id === selectedUserId) || sortedUsers[0] || null;
      const selectedCharacters = characters.filter(
        (character) => character.user_id === selectedUser?.id
      );
      const axisCharacterIds = selectedCharacters.map((character) => Number(character.id));
      if (!axisCharacterIds.includes(activeAxisCharacterId)) {
        activeAxisCharacterId = axisCharacterIds[0] ?? null;
        axisStateError = null;
      }
      const axisState =
        activeAxisCharacterId !== null ? axisStateCache.get(activeAxisCharacterId) : null;
      const axisStateLoadingActive =
        activeAxisCharacterId !== null && axisStateLoading.has(activeAxisCharacterId);

      root.innerHTML = `
        <div class="page">
          <div class="page-header">
            <div>
              <h2>Users</h2>
              <p class="muted">${sortedUsers.length} of ${users.length} users shown.</p>
            </div>
          </div>
          <div class="split-layout users-split">
            <div class="users-left">
              <div class="card table-card users-table-card">
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
                    <input type="checkbox" id="user-active-only" ${
                      activeOnly ? 'checked' : ''
                    } />
                    <span>Active only</span>
                  </label>
                </div>
                ${buildUsersTable(sortedUsers, sortState, selectedUser?.id)}
              </div>
              <div class="users-bottom-row">
                ${buildCreateUserCard(session.role)}
                <div class="detail-card users-placeholder-card">
                  <h3>Secondary Panel</h3>
                  <p class="muted">Reserved for additional tools.</p>
                </div>
              </div>
            </div>
            <aside class="detail-panel">
              ${buildUserDetails({
                user: selectedUser,
                characters,
                worldsById,
                permissionsByUser,
                locationsByCharacter,
                activeTab: activeDetailTab,
                axisState,
                axisCharacterId: activeAxisCharacterId,
                axisStateLoading: axisStateLoadingActive,
                axisStateError,
              })}
            </aside>
          </div>
        </div>
      `;

      const createForm = root.querySelector('[data-create-user]');
      if (createForm) {
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
            await load();
          } catch (err) {
            showToast(err instanceof Error ? err.message : 'Failed to create user.', 'error');
          }
        });
      }

      root.querySelectorAll('[data-user-actions]').forEach((container) => {
        const username = container.getAttribute('data-user-actions');
        container.querySelectorAll('button').forEach((button) => {
          button.addEventListener('click', (event) => {
            event.stopPropagation();
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

      root.querySelectorAll('th.sortable').forEach((header) => {
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

      root.querySelectorAll('tr[data-user-id]').forEach((row) => {
        row.addEventListener('click', () => {
          selectedUserId = Number(row.dataset.userId);
          renderPage();
        });
      });

      root.querySelectorAll('.tab-button[data-tab]').forEach((button) => {
        button.addEventListener('click', () => {
          activeDetailTab = button.dataset.tab;
          renderPage();
        });
      });

      const axisSelect = root.querySelector('[data-axis-character]');
      if (axisSelect) {
        axisSelect.addEventListener('change', (event) => {
          activeAxisCharacterId = Number(event.target.value);
          axisStateError = null;
          renderPage();
        });
      }

      const searchInput = root.querySelector('#user-search');
      if (searchInput) {
        searchInput.addEventListener('input', (event) => {
          searchTerm = event.target.value;
          renderPage();
        });
      }

      const activeToggle = root.querySelector('#user-active-only');
      if (activeToggle) {
        activeToggle.addEventListener('change', (event) => {
          activeOnly = event.target.checked;
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
        const tableWrap = root.querySelector('.table-wrap');
        if (tableWrap) {
          tableWrap.scrollTop = previousScrollTop;
        }
      }

      if (activeDetailTab === 'axis' && activeAxisCharacterId) {
        ensureAxisState(activeAxisCharacterId);
      }
    };

    renderPage();
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
