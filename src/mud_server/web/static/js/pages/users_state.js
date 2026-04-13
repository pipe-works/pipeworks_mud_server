/*
 * users_state.js
 *
 * Pure helpers for shaping the admin Users page view state. These helpers keep
 * table filtering/sorting and selection normalization out of the main page
 * controller so later data/render splits have a smaller surface to move.
 */

/**
 * Sort users based on the active sort state.
 *
 * @param {Array<object>} users
 * @param {{key: string, direction: string}} sortState
 * @returns {Array<object>}
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
    } else if (key === 'characters') {
      aVal = Number(a.character_count || 0);
      bVal = Number(b.character_count || 0);
    } else if (key === 'last_login') {
      aVal = a.last_login ? Date.parse(a.last_login) : 0;
      bVal = b.last_login ? Date.parse(b.last_login) : 0;
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

/**
 * Filter users based on the current search and visibility flags.
 *
 * @param {Array<object>} users
 * @param {string} searchTerm
 * @param {boolean} activeOnly
 * @param {boolean} onlineOnly
 * @returns {Array<object>}
 */
function filterUsers(users, searchTerm, activeOnly, onlineOnly) {
  // Keep the Active Users grid focused on currently manageable accounts.
  // Tombstoned users remain visible through explicit audit/table flows.
  let filtered = users.filter((user) => !user.tombstoned_at);
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
 * Build sorted world options from the metadata cache.
 *
 * @param {Map<string, string>} worldsById
 * @returns {Array<{id: string, name: string}>}
 */
function buildWorldOptions(worldsById) {
  return Array.from(worldsById.entries())
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id));
}

/**
 * Keep the selected user stable across refreshes while falling back to the
 * first visible row when needed.
 *
 * @param {Array<object>} sortedUsers
 * @param {number|null} selectedUserId
 * @returns {{selectedUserId: number|null, selectedUser: object|null}}
 */
function resolveSelectedUser(sortedUsers, selectedUserId) {
  let nextSelectedUserId = selectedUserId;
  if (sortedUsers.length === 0) {
    nextSelectedUserId = null;
  } else if (!nextSelectedUserId || !sortedUsers.some((user) => user.id === nextSelectedUserId)) {
    nextSelectedUserId = sortedUsers[0].id;
  }

  const selectedUser =
    sortedUsers.find((user) => user.id === nextSelectedUserId) || sortedUsers[0] || null;
  return { selectedUserId: nextSelectedUserId, selectedUser };
}

/**
 * Ensure the create-character world stays on a valid active-world option.
 *
 * @param {string} selectedWorldId
 * @param {Array<{id: string, name: string}>} worldOptions
 * @returns {string}
 */
function resolveCreateCharacterWorldId(selectedWorldId, worldOptions) {
  const availableWorldIds = new Set(worldOptions.map((world) => world.id));
  if (!selectedWorldId || !availableWorldIds.has(selectedWorldId)) {
    return worldOptions[0]?.id || '';
  }
  return selectedWorldId;
}

/**
 * Pull just the characters owned by the current selected user.
 *
 * @param {Array<object>} characters
 * @param {number|null|undefined} selectedUserId
 * @returns {Array<object>}
 */
function getSelectedUserCharacters(characters, selectedUserId) {
  return characters.filter((character) => character.user_id === selectedUserId);
}

/**
 * Keep the active axis selection on a valid character for the selected user.
 *
 * @param {Array<object>} selectedCharacters
 * @param {number|null} activeAxisCharacterId
 * @returns {number|null}
 */
function resolveActiveAxisCharacterId(selectedCharacters, activeAxisCharacterId) {
  const axisCharacterIds = selectedCharacters.map((character) => Number(character.id));
  if (!axisCharacterIds.includes(activeAxisCharacterId)) {
    return axisCharacterIds[0] ?? null;
  }
  return activeAxisCharacterId;
}

export {
  buildWorldOptions,
  filterUsers,
  getSelectedUserCharacters,
  resolveActiveAxisCharacterId,
  resolveCreateCharacterWorldId,
  resolveSelectedUser,
  sortUsers,
};
