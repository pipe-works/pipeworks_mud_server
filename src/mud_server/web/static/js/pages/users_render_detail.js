/*
 * users_render_detail.js
 *
 * Detail-region render helpers for the admin Users page.
 */

import { renderTable } from '../ui/table.js';
import { buildCreateCharacterPanel } from './users_create_character.js';
import { buildAxisStatePanel } from './users_axis_panel.js';
import { escapeHtml, formatDate, formatRole } from './users_render_shared.js';

/**
 * Build character-management buttons for a character row.
 *
 * Only superusers may remove characters, so lower roles receive no controls.
 *
 * @param {number|string} characterId
 * @param {string} characterName
 * @param {string} role
 * @param {string|null} pendingActionKey
 * @returns {string}
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
        class="btn btn--secondary btn--sm"
        data-character-action="tombstone"
        data-character-id="${characterId}"
        data-character-name="${escapeHtml(characterName)}"
        ${pendingActionKey === tombstoneKey ? 'disabled' : ''}
      >
        ${pendingActionKey === tombstoneKey ? 'Tombstoning...' : 'Tombstone'}
      </button>
      <button
        class="btn btn--secondary btn--sm"
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

/**
 * Build the detail panel for the selected user.
 *
 * @param {object} params
 * @returns {string}
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
        <p class="u-muted">Select a user to see account details.</p>
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
    : '<p class="u-muted">No characters found.</p>';

  const worldsHtml = worldAccess.length
    ? worldAccess
        .map((worldId) => {
          const worldName = worldsById.get(worldId) || worldId;
          return `<span class="tag">${worldName}</span>`;
        })
        .join('')
    : '<p class="u-muted">No world permissions recorded.</p>';

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
            ? '<p class="u-muted detail-help">Superusers may tombstone or permanently delete characters.</p>'
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
 *
 * @param {string} role
 * @returns {string}
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
          <input class="input" type="text" name="username" required />
        </label>
        <label>
          Role
          <select class="select" name="role">
            ${roleOptions.map((opt) => `<option value="${opt}">${opt}</option>`).join('')}
          </select>
        </label>
        <label>
          Password
          <input class="input" type="password" name="password" required />
        </label>
        <label>
          Confirm Password
          <input class="input" type="password" name="password_confirm" required />
        </label>
        <button class="btn btn--primary" type="submit">Create account</button>
      </form>
      <p class="u-muted detail-help">Admins can create players/worldbuilders. Superusers can create all roles.</p>
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
 *
 * @param {Array<object>} characters
 * @param {Map<string, string>} worldsById
 * @returns {string}
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
        <p class="u-muted">No tombstoned characters recorded.</p>
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
      <p class="u-muted">Most recent tombstoned character records for audit/recovery workflows.</p>
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
 *
 * @param {string} role
 * @returns {string}
 */
function buildUsersPageShell(role) {
  return `
    <div class="page">
      <div class="page-header">
        <div>
          <h2>Users</h2>
          <p class="u-muted" data-users-count>Loading users...</p>
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

export { buildUserDetails, buildTombstonedCharactersCard, buildUsersPageShell };
