/*
 * tombstones.js
 *
 * Dedicated tombstone dashboard for archival account/character inspection.
 * This view is intentionally read-only and separates historical rows from the
 * Active Users operational workflow.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

/**
 * Convert table payload rows into object rows.
 *
 * @param {string[]} columns
 * @param {Array<Array<unknown>>} rows
 * @returns {Array<Record<string, unknown>>}
 */
function rowsToObjects(columns, rows) {
  return rows.map((row) => {
    const record = {};
    columns.forEach((column, index) => {
      record[column] = row[index];
    });
    return record;
  });
}

/**
 * Escape HTML-sensitive characters.
 *
 * @param {unknown} value
 * @returns {string}
 */
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

/**
 * Format optional timestamp display.
 *
 * @param {unknown} value
 * @returns {string}
 */
function formatDate(value) {
  if (!value) {
    return '—';
  }
  return String(value);
}

/**
 * Build tombstoned users table rows.
 *
 * @param {Array<Record<string, unknown>>} users
 * @returns {string[][]}
 */
function buildTombstonedUserRows(users) {
  return users.map((user) => [
    escapeHtml(user.id),
    escapeHtml(user.username),
    escapeHtml(user.role),
    escapeHtml(formatDate(user.tombstoned_at)),
    escapeHtml(formatDate(user.last_login)),
  ]);
}

/**
 * Build tombstoned character rows.
 *
 * @param {Array<Record<string, unknown>>} characters
 * @param {Map<string, string>} worldNameById
 * @returns {string[][]}
 */
function buildTombstonedCharacterRows(characters, worldNameById) {
  return characters.map((character) => {
    const worldId = String(character.world_id || '');
    const worldName = worldNameById.get(worldId) || worldId || '—';
    return [
      escapeHtml(character.id),
      escapeHtml(character.name || '—'),
      escapeHtml(worldName),
      escapeHtml(formatDate(character.updated_at || character.created_at)),
    ];
  });
}

/**
 * Return true when a character row follows tombstone conventions.
 *
 * @param {Record<string, unknown>} character
 * @returns {boolean}
 */
function isTombstonedCharacter(character) {
  const detachedOwner = character.user_id === null || character.user_id === undefined;
  const tombstoneName =
    typeof character.name === 'string' && character.name.startsWith('tombstone_');
  return detachedOwner && tombstoneName;
}

/**
 * Render dedicated tombstone dashboard.
 */
async function renderTombstonesDashboard(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Tombstones</h1>
      <p class="u-muted">Loading tombstone dashboard...</p>
    </div>
  `;

  const sessionId = session.session_id;
  let tombstonedUsers = [];
  let tombstonedCharacters = [];
  let worldNameById = new Map();
  let searchTerm = '';

  /**
   * Fetch archival datasets from raw table endpoints.
   *
   * We intentionally avoid /admin/database/players here because that endpoint
   * is now scoped to active accounts by design.
   */
  const load = async () => {
    const [usersResponse, charactersResponse, worldsResponse] = await Promise.all([
      api.getTableRows(sessionId, 'users', 4000),
      api.getTableRows(sessionId, 'characters', 4000),
      api.getTableRows(sessionId, 'worlds', 300),
    ]);

    const users = rowsToObjects(usersResponse.columns, usersResponse.rows);
    const characters = rowsToObjects(charactersResponse.columns, charactersResponse.rows);
    const worlds = rowsToObjects(worldsResponse.columns, worldsResponse.rows);
    worldNameById = new Map(worlds.map((world) => [String(world.id), String(world.name)]));

    tombstonedUsers = users
      .filter((user) => Boolean(user.tombstoned_at))
      .sort((a, b) => String(b.tombstoned_at || '').localeCompare(String(a.tombstoned_at || '')));

    tombstonedCharacters = characters
      .filter((character) => isTombstonedCharacter(character))
      .sort((a, b) =>
        String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || ''))
      );
  };

  const render = () => {
    const term = searchTerm.trim().toLowerCase();

    const filteredUsers = term
      ? tombstonedUsers.filter((user) =>
          [user.username, user.role, user.account_origin].filter(Boolean).join(' ').toLowerCase().includes(term)
        )
      : tombstonedUsers;

    const filteredCharacters = term
      ? tombstonedCharacters.filter((character) => {
          const worldId = String(character.world_id || '');
          const worldName = worldNameById.get(worldId) || worldId;
          return [character.name, worldName].filter(Boolean).join(' ').toLowerCase().includes(term);
        })
      : tombstonedCharacters;

    const userTable = filteredUsers.length
      ? renderTable(
          ['ID', 'Username', 'Role', 'Tombstoned', 'Last Login'],
          buildTombstonedUserRows(filteredUsers)
        )
      : '<p class="u-muted">No tombstoned account rows match this filter.</p>';

    const characterTable = filteredCharacters.length
      ? renderTable(
          ['ID', 'Character', 'World', 'Updated'],
          buildTombstonedCharacterRows(filteredCharacters, worldNameById)
        )
      : '<p class="u-muted">No tombstoned character rows match this filter.</p>';

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Tombstone Dashboard</h2>
            <p class="u-muted">
              ${filteredUsers.length} tombstoned accounts • ${filteredCharacters.length} tombstoned characters
            </p>
          </div>
          <div class="actions">
            <button class="btn btn--secondary" type="button" data-tombstones-refresh>Refresh</button>
          </div>
        </div>
        <div class="card table-card">
          <div class="table-toolbar dashboard-toolbar">
            <label class="table-search">
              <span>Search</span>
              <input
                class="input"
                type="search"
                value="${escapeHtml(searchTerm)}"
                placeholder="username, role, character, world"
                data-tombstones-search
              />
            </label>
          </div>
          <h3>Tombstoned Accounts</h3>
          ${userTable}
        </div>
        <div class="card table-card">
          <h3>Tombstoned Characters</h3>
          ${characterTable}
        </div>
      </div>
    `;

    const searchInput = root.querySelector('[data-tombstones-search]');
    if (searchInput) {
      searchInput.addEventListener('input', (event) => {
        searchTerm = event.target.value;
        render();
      });
    }

    const refreshButton = root.querySelector('[data-tombstones-refresh]');
    if (refreshButton) {
      refreshButton.addEventListener('click', async () => {
        try {
          await load();
          render();
          showToast('Tombstone dashboard refreshed.', 'success');
        } catch (error) {
          showToast(error instanceof Error ? error.message : 'Failed to refresh tombstone dashboard.', 'error');
        }
      });
    }
  };

  try {
    await load();
    render();
  } catch (error) {
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Tombstones</h1>
        <p class="error">${
          error instanceof Error ? escapeHtml(error.message) : 'Failed to load tombstone dashboard.'
        }</p>
      </div>
    `;
  }
}

export { renderTombstonesDashboard };
