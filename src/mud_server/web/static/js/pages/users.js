/*
 * users.js
 *
 * Admin users view. Lists users and supports basic management actions.
 */

import { showToast } from '../ui/toasts.js';
import {
  bindCreateCharacterPanel,
} from './users_create_character.js';
import { handleCharacterAction, handleUserAction } from './users_actions.js';
import { loadUsersList, loadUsersMetadata } from './users_data.js';
import {
  buildUserDetails,
  buildTombstonedCharactersCard,
  buildUsersPageShell,
} from './users_render_detail.js';
import { buildUsersTable } from './users_render_table.js';
import {
  buildWorldOptions,
  filterUsers,
  getSelectedUserCharacters,
  resolveActiveAxisCharacterId,
  resolveCreateCharacterWorldId,
  resolveSelectedUser,
  sortUsers,
} from './users_state.js';

async function renderUsers(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Users</h1>
      <p class="u-muted">Loading users...</p>
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
      <div class="auth-panel wide">
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
    const nextUsersState = await loadUsersList({ api, sessionId });
    users = nextUsersState.users;
    lastRefreshAt = nextUsersState.lastRefreshAt;
  };

  /**
   * Pull metadata tables needed for the right-side details panel.
   */
  const loadMetadata = async ({ showErrorToast = true } = {}) => {
    try {
      const metadata = await loadUsersMetadata({ api, sessionId });
      characters = metadata.characters;
      worldsById = metadata.worldsById;
      permissionsByUser = metadata.permissionsByUser;
      locationsByCharacter = metadata.locationsByCharacter;
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

  const refreshUsersOnly = async () => refreshData({ includeMetadata: false, showErrorToast: false });
  const refreshUsersAndMetadata = async () =>
    refreshData({ includeMetadata: true, showErrorToast: false });

  // Bind once against stable regions so auto-refresh can replace their HTML
  // without rebuilding the same event listeners on every render.
  tableRegion.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    const actionButton = event.target.closest('[data-user-actions] button[data-action]');
    if (actionButton && tableRegion.contains(actionButton)) {
      event.stopPropagation();
      const action = actionButton.getAttribute('data-action');
      const actionContainer = actionButton.closest('[data-user-actions]');
      const username = actionContainer?.getAttribute('data-user-actions');
      if (!action || !username) {
        return;
      }
      void handleUserAction({
        api,
        sessionId,
        action,
        username,
        refresh: refreshUsersOnly,
      });
      return;
    }

    const sortHeader = event.target.closest('th.sortable[data-sort-key]');
    if (sortHeader && tableRegion.contains(sortHeader)) {
      const key = sortHeader.getAttribute('data-sort-key');
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
      return;
    }

    const row = event.target.closest('tr[data-user-id]');
    if (row && tableRegion.contains(row)) {
      selectedUserId = Number(row.getAttribute('data-user-id'));
      renderPage();
    }
  });

  tableRegion.addEventListener('input', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    if (target.id === 'user-search') {
      searchTerm = target.value;
      renderPage();
    }
  });

  tableRegion.addEventListener('change', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    if (target.id === 'user-active-only') {
      activeOnly = target.checked;
      renderPage();
      return;
    }
    if (target.id === 'user-online-only') {
      onlineOnly = target.checked;
      renderPage();
    }
  });

  detailRegion.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    const tabButton = event.target.closest('.tab-button[data-tab]');
    if (tabButton && detailRegion.contains(tabButton)) {
      activeDetailTab = tabButton.getAttribute('data-tab');
      renderPage();
      return;
    }

    const characterButton = event.target.closest('[data-character-action]');
    if (characterButton && detailRegion.contains(characterButton)) {
      event.stopPropagation();
      const action = characterButton.getAttribute('data-character-action');
      const characterId = characterButton.getAttribute('data-character-id');
      const characterName = characterButton.getAttribute('data-character-name') || 'character';
      if (!action || !characterId) {
        return;
      }
      void handleCharacterAction({
        api,
        sessionId,
        action,
        characterId,
        characterName,
        refresh: refreshUsersAndMetadata,
        setPendingActionKey: (value) => {
          characterActionPending = value;
          renderPage();
        },
      });
    }
  });

  detailRegion.addEventListener('change', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
      return;
    }
    if (target.hasAttribute('data-axis-character')) {
      activeAxisCharacterId = Number(target.value);
      axisStateError = null;
      axisEventsError = null;
      renderPage();
    }
  });

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
    const selection = resolveSelectedUser(sortedUsers, selectedUserId);
    selectedUserId = selection.selectedUserId;
    const selectedUser = selection.selectedUser;
    const worldOptions = buildWorldOptions(worldsById);
    createCharacterWorldId = resolveCreateCharacterWorldId(createCharacterWorldId, worldOptions);
    const selectedCharacters = getSelectedUserCharacters(characters, selectedUser?.id);
    const nextAxisCharacterId = resolveActiveAxisCharacterId(selectedCharacters, activeAxisCharacterId);
    if (nextAxisCharacterId !== activeAxisCharacterId) {
      activeAxisCharacterId = nextAxisCharacterId;
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
        await refreshUsersAndMetadata();
      },
      onError: (error) => {
        showToast(error instanceof Error ? error.message : 'Failed to create character.', 'error');
      },
    });

    const searchInput = tableRegion.querySelector('#user-search');

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
      <div class="auth-panel wide">
        <h1>Users</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load users.'}</p>
      </div>
    `;
  }
}

export { renderUsers };
