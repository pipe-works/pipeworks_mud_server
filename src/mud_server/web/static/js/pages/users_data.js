/*
 * users_data.js
 *
 * Data-loading helpers for the admin Users page. These helpers isolate the
 * server-fetch and table-normalization layer from the page controller.
 */

/**
 * Convert tabular rows (column list + row arrays) into objects.
 *
 * @param {Array<string>} columns
 * @param {Array<Array<unknown>>} rows
 * @returns {Array<object>}
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

/**
 * Fetch the primary users list used by the left-hand table.
 *
 * @param {object} params
 * @param {object} params.api
 * @param {string} params.sessionId
 * @returns {Promise<{users: Array<object>, lastRefreshAt: Date}>}
 */
async function loadUsersList({ api, sessionId }) {
  const response = await api.getPlayers(sessionId);
  return {
    users: Array.isArray(response.players) ? response.players : [],
    lastRefreshAt: new Date(),
  };
}

/**
 * Fetch metadata tables needed by the details and provisioning panels.
 *
 * @param {object} params
 * @param {object} params.api
 * @param {string} params.sessionId
 * @returns {Promise<{
 *   characters: Array<object>,
 *   worldsById: Map<string, string>,
 *   permissionsByUser: Map<number, Array<string>>,
 *   locationsByCharacter: Map<number, object>
 * }>}
 */
async function loadUsersMetadata({ api, sessionId }) {
  const [charactersResp, worldsResp, permissionsResp, locationsResp] = await Promise.all([
    api.getAllTableRows(sessionId, 'characters'),
    api.getTableRows(sessionId, 'worlds', 200),
    api.getAllTableRows(sessionId, 'world_permissions'),
    api.getAllTableRows(sessionId, 'character_locations'),
  ]);

  const worldRows = rowsToObjects(worldsResp.columns, worldsResp.rows);
  const worldsById = new Map(worldRows.map((world) => [world.id, world.name]));

  const characters = rowsToObjects(charactersResp.columns, charactersResp.rows);
  const permissions = rowsToObjects(permissionsResp.columns, permissionsResp.rows);
  const locations = rowsToObjects(locationsResp.columns, locationsResp.rows);

  const permissionsByUser = new Map();
  permissions
    .filter((entry) => entry.can_access)
    .forEach((entry) => {
      const existing = permissionsByUser.get(entry.user_id) || [];
      existing.push(entry.world_id);
      permissionsByUser.set(entry.user_id, existing);
    });

  const locationsByCharacter = new Map(
    locations.map((location) => [location.character_id, location])
  );

  return {
    characters,
    worldsById,
    permissionsByUser,
    locationsByCharacter,
  };
}

export { loadUsersList, loadUsersMetadata };
