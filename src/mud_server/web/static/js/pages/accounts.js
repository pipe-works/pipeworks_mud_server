/*
 * accounts.js
 *
 * Dedicated account dashboard for Section 2 of the admin workflow.
 * This view intentionally focuses on account-centric inspection:
 * - account role/origin/status
 * - online presence
 * - linked characters
 * - world access footprint
 */

import { showToast } from '../ui/toasts.js';

/**
 * Convert a database table payload (columns + row arrays) to object rows.
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
 * Escape untrusted values before HTML injection.
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
 * Present optional timestamps safely.
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
 * Present account role in title case for readability.
 *
 * @param {unknown} role
 * @returns {string}
 */
function formatRole(role) {
  if (!role) {
    return 'Unknown';
  }
  const raw = String(role);
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

/**
 * Render account status pills.
 *
 * @param {Record<string, unknown>} account
 * @returns {string}
 */
function buildStatusPills(account) {
  const accountClass = account.is_online_account ? 'is-online' : 'is-offline';
  const worldClass = account.is_online_in_world ? 'is-online' : 'is-offline';
  return `
    <div class="status-stack">
      <span class="status-pill ${accountClass}">Account</span>
      <span class="status-pill ${worldClass}">In-world</span>
    </div>
  `;
}

/**
 * Build selectable accounts table.
 *
 * @param {Array<Record<string, unknown>>} accounts
 * @param {number|null} selectedAccountId
 * @returns {string}
 */
function buildAccountsTable(accounts, selectedAccountId) {
  const rowsHtml = accounts.length
    ? accounts
        .map((account) => {
          const accountId = Number(account.id);
          const isSelected = selectedAccountId === accountId;
          const rowClass = [
            'is-selectable',
            isSelected ? 'is-selected' : '',
            account.is_online_in_world ? 'is-in-world' : '',
          ]
            .filter(Boolean)
            .join(' ');
          return `
            <tr class="${rowClass}" data-account-id="${accountId}">
              <td>${escapeHtml(account.username)}</td>
              <td>${escapeHtml(formatRole(account.role))}</td>
              <td>${buildStatusPills(account)}</td>
              <td>${Number(account.character_count || 0)}</td>
              <td>${escapeHtml(formatDate(account.last_login))}</td>
            </tr>
          `;
        })
        .join('')
    : `
      <tr>
        <td class="table-empty" colspan="5">No accounts match this filter.</td>
      </tr>
    `;

  return `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Role</th>
            <th>Online</th>
            <th>Characters</th>
            <th>Last Login</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

/**
 * Build detailed account panel for the selected row.
 *
 * @param {Record<string, unknown>|null} account
 * @param {Array<Record<string, unknown>>} accountCharacters
 * @param {Map<string, string>} worldNameById
 * @param {string[]} worldAccess
 * @returns {string}
 */
function buildAccountDetails(account, accountCharacters, worldNameById, worldAccess) {
  if (!account) {
    return `
      <div class="detail-card dashboard-detail-card">
        <h3>Account Details</h3>
        <p class="muted">Select an account to inspect details.</p>
      </div>
    `;
  }

  const worldAccessTags = worldAccess.length
    ? worldAccess
        .map((worldId) => {
          const worldName = worldNameById.get(worldId) || worldId;
          return `<span class="tag">${escapeHtml(worldName)}</span>`;
        })
        .join('')
    : '<p class="muted">No world access rows recorded.</p>';

  const characterRows = accountCharacters.length
    ? accountCharacters
        .map((character) => {
          const worldId = String(character.world_id || '');
          const worldName = worldNameById.get(worldId) || worldId || '—';
          return `
            <div class="detail-row">
              <div>
                <div class="detail-title">${escapeHtml(character.name || '—')}</div>
                <div class="detail-sub">${escapeHtml(worldName)}</div>
              </div>
              <div class="detail-meta">ID ${escapeHtml(character.id)}</div>
            </div>
          `;
        })
        .join('')
    : '<p class="muted">No linked characters.</p>';

  return `
    <div class="detail-card dashboard-detail-card">
      <h3>Account Details</h3>
      <dl class="detail-list">
        <div><dt>ID</dt><dd>${escapeHtml(account.id)}</dd></div>
        <div><dt>Username</dt><dd>${escapeHtml(account.username)}</dd></div>
        <div><dt>Role</dt><dd>${escapeHtml(formatRole(account.role))}</dd></div>
        <div><dt>Origin</dt><dd>${escapeHtml(account.account_origin || '—')}</dd></div>
        <div><dt>Guest</dt><dd>${account.is_guest ? 'Yes' : 'No'}</dd></div>
        <div><dt>Active</dt><dd>${account.is_active ? 'Yes' : 'No'}</dd></div>
        <div><dt>Account Online</dt><dd>${account.is_online_account ? 'Yes' : 'No'}</dd></div>
        <div><dt>In-world</dt><dd>${account.is_online_in_world ? 'Yes' : 'No'}</dd></div>
        <div><dt>Created</dt><dd>${escapeHtml(formatDate(account.created_at))}</dd></div>
        <div><dt>Last Login</dt><dd>${escapeHtml(formatDate(account.last_login))}</dd></div>
      </dl>
      <h4>World Access</h4>
      <div class="tag-list">${worldAccessTags}</div>
      <h4>Linked Characters</h4>
      <div class="dashboard-scroll-region">${characterRows}</div>
    </div>
  `;
}

/**
 * Render dedicated account dashboard.
 */
async function renderAccountsDashboard(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Accounts</h1>
      <p class="muted">Loading account dashboard...</p>
    </div>
  `;

  const sessionId = session.session_id;
  let allAccounts = [];
  let allCharacters = [];
  let worldNameById = new Map();
  let worldAccessByUser = new Map();

  let selectedAccountId = null;
  let searchTerm = '';
  let roleFilter = 'all';
  let onlineOnly = false;

  /**
   * Load account + metadata sources needed for this dashboard.
   *
   * We intentionally source accounts from /admin/database/players because that
   * endpoint already enforces "active non-tombstoned account" semantics.
   */
  const load = async () => {
    const [accountsResponse, charactersResponse, worldsResponse, worldPermsResponse] =
      await Promise.all([
        api.getPlayers(sessionId),
        api.getTableRows(sessionId, 'characters', 2000),
        api.getTableRows(sessionId, 'worlds', 300),
        api.getTableRows(sessionId, 'world_permissions', 2000),
      ]);

    allAccounts = Array.isArray(accountsResponse.players) ? accountsResponse.players : [];
    allCharacters = rowsToObjects(charactersResponse.columns, charactersResponse.rows);

    const worlds = rowsToObjects(worldsResponse.columns, worldsResponse.rows);
    worldNameById = new Map(worlds.map((world) => [String(world.id), String(world.name)]));

    const worldPerms = rowsToObjects(worldPermsResponse.columns, worldPermsResponse.rows);
    worldAccessByUser = new Map();
    worldPerms
      .filter((row) => Boolean(row.can_access))
      .forEach((row) => {
        const userId = Number(row.user_id);
        const worldId = String(row.world_id || '');
        if (!worldId) {
          return;
        }
        const existing = worldAccessByUser.get(userId) || [];
        existing.push(worldId);
        worldAccessByUser.set(userId, existing);
      });
  };

  const render = () => {
    const filteredAccounts = allAccounts
      .filter((account) => {
        if (roleFilter !== 'all' && String(account.role || '') !== roleFilter) {
          return false;
        }
        if (onlineOnly && !account.is_online_account && !account.is_online_in_world) {
          return false;
        }
        const haystack = [account.username, account.role, account.account_origin]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(searchTerm.trim().toLowerCase());
      })
      .sort((a, b) => String(a.username).localeCompare(String(b.username)));

    if (!filteredAccounts.length) {
      selectedAccountId = null;
    } else if (!filteredAccounts.some((account) => Number(account.id) === selectedAccountId)) {
      selectedAccountId = Number(filteredAccounts[0].id);
    }

    const selectedAccount =
      filteredAccounts.find((account) => Number(account.id) === selectedAccountId) || null;

    const selectedCharacters = selectedAccount
      ? allCharacters
          .filter((character) => Number(character.user_id) === Number(selectedAccount.id))
          .sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')))
      : [];

    const explicitWorldAccess = selectedAccount
      ? worldAccessByUser.get(Number(selectedAccount.id)) || []
      : [];
    const inferredWorldAccess = selectedCharacters
      .map((character) => String(character.world_id || ''))
      .filter(Boolean);
    const worldAccess = [...new Set([...explicitWorldAccess, ...inferredWorldAccess])].sort();

    const roles = [...new Set(allAccounts.map((account) => String(account.role || '')))]
      .filter(Boolean)
      .sort();

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Account Dashboard</h2>
            <p class="muted">${filteredAccounts.length} of ${allAccounts.length} accounts shown.</p>
          </div>
          <div class="actions">
            <button type="button" data-accounts-refresh>Refresh</button>
          </div>
        </div>
        <div class="split-layout dashboard-split">
          <div class="dashboard-left">
            <div class="card table-card dashboard-table-card">
              <h3>Account Registry</h3>
              <div class="table-toolbar dashboard-toolbar">
                <label class="table-search">
                  <span>Search</span>
                  <input type="search" value="${escapeHtml(
                    searchTerm
                  )}" placeholder="username, role, origin" data-accounts-search />
                </label>
                <label class="detail-form dashboard-select-inline">
                  Role
                  <select data-accounts-role>
                    <option value="all" ${roleFilter === 'all' ? 'selected' : ''}>All</option>
                    ${roles
                      .map(
                        (role) =>
                          `<option value="${escapeHtml(role)}" ${
                            roleFilter === role ? 'selected' : ''
                          }>${escapeHtml(formatRole(role))}</option>`
                      )
                      .join('')}
                  </select>
                </label>
                <label class="table-toggle">
                  <input type="checkbox" ${onlineOnly ? 'checked' : ''} data-accounts-online />
                  <span>Online only</span>
                </label>
              </div>
              ${buildAccountsTable(filteredAccounts, selectedAccountId)}
            </div>
          </div>
          <aside class="detail-panel dashboard-right">
            ${buildAccountDetails(selectedAccount, selectedCharacters, worldNameById, worldAccess)}
          </aside>
        </div>
      </div>
    `;

    const searchInput = root.querySelector('[data-accounts-search]');
    if (searchInput) {
      searchInput.addEventListener('input', (event) => {
        searchTerm = event.target.value;
        render();
      });
    }

    const roleSelect = root.querySelector('[data-accounts-role]');
    if (roleSelect) {
      roleSelect.addEventListener('change', (event) => {
        roleFilter = event.target.value;
        render();
      });
    }

    const onlineToggle = root.querySelector('[data-accounts-online]');
    if (onlineToggle) {
      onlineToggle.addEventListener('change', (event) => {
        onlineOnly = event.target.checked;
        render();
      });
    }

    root.querySelectorAll('[data-account-id]').forEach((row) => {
      row.addEventListener('click', () => {
        selectedAccountId = Number(row.getAttribute('data-account-id'));
        render();
      });
    });

    const refreshButton = root.querySelector('[data-accounts-refresh]');
    if (refreshButton) {
      refreshButton.addEventListener('click', async () => {
        try {
          await load();
          render();
          showToast('Account dashboard refreshed.', 'success');
        } catch (error) {
          showToast(error instanceof Error ? error.message : 'Failed to refresh account dashboard.', 'error');
        }
      });
    }
  };

  try {
    await load();
    render();
  } catch (error) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Accounts</h1>
        <p class="error">${
          error instanceof Error ? escapeHtml(error.message) : 'Failed to load account dashboard.'
        }</p>
      </div>
    `;
  }
}

export { renderAccountsDashboard };
