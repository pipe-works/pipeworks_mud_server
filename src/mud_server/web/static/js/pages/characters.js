/*
 * characters.js
 *
 * Dedicated character dashboard requested in Section 2.
 * This view focuses on world-facing identities (characters), including:
 * - owner linkage
 * - world/location context
 * - state seed/version metadata
 * - axis state + recent axis event history
 */

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
 * Escape untrusted values before HTML rendering.
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
 * Format optional timestamp values.
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
 * Format optional numeric axis values.
 *
 * @param {unknown} score
 * @returns {string}
 */
function formatAxisScore(score) {
  if (typeof score !== 'number') {
    return '—';
  }
  return score.toFixed(2);
}

/**
 * Convert technical event key to readable title.
 *
 * @param {unknown} eventType
 * @returns {string}
 */
function formatEventTypeLabel(eventType) {
  if (!eventType) {
    return 'Event';
  }
  return String(eventType)
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/**
 * Produce concise "what happened" summary for an axis event.
 *
 * @param {Record<string, unknown>} event
 * @returns {string}
 */
function buildAxisEventSummary(event) {
  const description =
    event?.event_type_description && String(event.event_type_description).trim();
  if (description) {
    return description;
  }

  const metadata = event?.metadata || {};
  const summary = metadata.summary || metadata.reason || metadata.message || '';
  if (summary) {
    return String(summary);
  }

  const deltas = Array.isArray(event?.deltas) ? event.deltas : [];
  if (deltas.length === 1) {
    const delta = deltas[0] || {};
    const axisName = delta.axis_name ? String(delta.axis_name) : 'Axis';
    const amount = Number(delta.delta);
    if (Number.isFinite(amount)) {
      if (amount > 0) {
        return `${axisName} increased by ${formatAxisScore(amount)}`;
      }
      if (amount < 0) {
        return `${axisName} decreased by ${formatAxisScore(Math.abs(amount))}`;
      }
    }
    return `${axisName} was updated`;
  }

  if (deltas.length > 1) {
    return `${deltas.length} axis values updated`;
  }

  return 'No additional event details.';
}

/**
 * Determine whether a character row is tombstoned.
 *
 * Tombstoned rows are intentionally omitted from this dashboard and surfaced
 * through the dedicated tombstone dashboard.
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
 * Build selectable character table.
 *
 * @param {Array<Record<string, unknown>>} characters
 * @param {number|null} selectedCharacterId
 * @param {Map<number, Record<string, unknown>>} userById
 * @param {Map<string, string>} worldNameById
 * @param {Map<number, Record<string, unknown>>} locationByCharacterId
 * @returns {string}
 */
function buildCharactersTable(
  characters,
  selectedCharacterId,
  userById,
  worldNameById,
  locationByCharacterId
) {
  const rowsHtml = characters.length
    ? characters
        .map((character) => {
          const characterId = Number(character.id);
          const owner = userById.get(Number(character.user_id));
          const worldId = String(character.world_id || '');
          const worldName = worldNameById.get(worldId) || worldId || '—';
          const room = locationByCharacterId.get(characterId)?.room_id || '—';
          const rowClass = ['is-selectable', selectedCharacterId === characterId ? 'is-selected' : '']
            .filter(Boolean)
            .join(' ');
          return `
            <tr class="${rowClass}" data-character-id="${characterId}">
              <td>${escapeHtml(character.name || '—')}</td>
              <td>${escapeHtml(owner?.username || 'Detached')}</td>
              <td>${escapeHtml(worldName)}</td>
              <td>${escapeHtml(room)}</td>
              <td>${escapeHtml(formatDate(character.updated_at || character.created_at))}</td>
            </tr>
          `;
        })
        .join('')
    : `
      <tr>
        <td class="table-empty" colspan="5">No characters match this filter.</td>
      </tr>
    `;

  return `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Character</th>
            <th>Owner</th>
            <th>World</th>
            <th>Room</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

/**
 * Build axis event cards for selected character.
 *
 * @param {Array<Record<string, unknown>>} events
 * @returns {string}
 */
function buildAxisEvents(events) {
  if (!events || events.length === 0) {
    return '<p class="u-muted">No axis events recorded.</p>';
  }

  return events
    .map((event) => {
      const eventTitle = formatEventTypeLabel(event.event_type);
      const summary = buildAxisEventSummary(event);
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
        : '<p class="u-muted">No metadata.</p>';

      const deltas = Array.isArray(event.deltas) ? event.deltas : [];
      const deltaHtml = deltas.length
        ? deltas
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
            .join('')
        : '<p class="u-muted">No deltas.</p>';

      return `
        <div class="axis-event">
          <div class="axis-event-header">
            <div>
              <div class="axis-event-title">${escapeHtml(eventTitle)}</div>
              <div class="axis-event-kind">${escapeHtml(event.event_type || '')}</div>
              <div class="axis-event-summary">${escapeHtml(summary)}</div>
              <div class="axis-event-sub">${escapeHtml(event.timestamp || '—')}</div>
            </div>
            <div class="axis-event-world">${escapeHtml(event.world_id || '—')}</div>
          </div>
          <div class="axis-event-deltas">${deltaHtml}</div>
          ${metadataHtml}
        </div>
      `;
    })
    .join('');
}

/**
 * Build detailed character panel for selected row.
 *
 * @param {Record<string, unknown>|null} character
 * @param {Map<number, Record<string, unknown>>} userById
 * @param {Map<string, string>} worldNameById
 * @param {Map<number, Record<string, unknown>>} locationByCharacterId
 * @param {Record<string, unknown>|null} axisState
 * @param {Array<Record<string, unknown>>|null} axisEvents
 * @param {boolean} axisLoading
 * @param {string|null} axisError
 * @returns {string}
 */
function buildCharacterDetails(
  character,
  userById,
  worldNameById,
  locationByCharacterId,
  axisState,
  axisEvents,
  axisLoading,
  axisError
) {
  if (!character) {
    return `
      <div class="detail-card dashboard-detail-card">
        <h3>Character Details</h3>
        <p class="u-muted">Select a character to inspect details.</p>
      </div>
    `;
  }

  const owner = userById.get(Number(character.user_id));
  const worldId = String(character.world_id || '');
  const worldName = worldNameById.get(worldId) || worldId || '—';
  const room = locationByCharacterId.get(Number(character.id))?.room_id || '—';

  const axisScoreRows =
    axisState && Array.isArray(axisState.axes) && axisState.axes.length
      ? axisState.axes
          .map(
            (axis) => `
              <div>
                <dt>${escapeHtml(axis.axis_name)}</dt>
                <dd>${escapeHtml(axis.axis_label || '—')} (${formatAxisScore(axis.axis_score)})</dd>
              </div>
            `
          )
          .join('')
      : '<p class="u-muted">No axis scores available.</p>';

  return `
    <div class="detail-card dashboard-detail-card">
      <h3>Character Details</h3>
      <dl class="detail-list">
        <div><dt>ID</dt><dd>${escapeHtml(character.id)}</dd></div>
        <div><dt>Name</dt><dd>${escapeHtml(character.name || '—')}</dd></div>
        <div><dt>Owner</dt><dd>${escapeHtml(owner?.username || 'Detached')}</dd></div>
        <div><dt>World</dt><dd>${escapeHtml(worldName)}</dd></div>
        <div><dt>Room</dt><dd>${escapeHtml(room)}</dd></div>
        <div><dt>Created</dt><dd>${escapeHtml(formatDate(character.created_at))}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(formatDate(character.updated_at))}</dd></div>
        <div><dt>Seed</dt><dd>${escapeHtml(character.state_seed ?? '—')}</dd></div>
        <div><dt>Policy</dt><dd>${escapeHtml(character.state_version || '—')}</dd></div>
      </dl>
      <h4>Axis State</h4>
      ${
        axisLoading
          ? '<p class="u-muted">Loading axis state...</p>'
          : axisError
            ? `<p class="error">${escapeHtml(axisError)}</p>`
            : `<dl class="detail-list axis-score-list">${axisScoreRows}</dl>`
      }
      <h4>Recent Axis Events</h4>
      <div class="axis-event-list">${buildAxisEvents(axisEvents || [])}</div>
    </div>
  `;
}

/**
 * Render dedicated character dashboard.
 */
async function renderCharactersDashboard(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Characters</h1>
      <p class="u-muted">Loading character dashboard...</p>
    </div>
  `;

  const sessionId = session.session_id;

  let allCharacters = [];
  let userById = new Map();
  let worldNameById = new Map();
  let locationByCharacterId = new Map();
  let selectedCharacterId = null;
  let searchTerm = '';
  let worldFilter = 'all';

  const axisStateByCharacter = new Map();
  const axisEventsByCharacter = new Map();
  const axisLoadingCharacterIds = new Set();
  const axisErrorByCharacter = new Map();

  /**
   * Fetch character dashboard data sources.
   */
  const load = async () => {
    const [charactersResponse, usersResponse, worldsResponse, locationsResponse] = await Promise.all([
      api.getTableRows(sessionId, 'characters', 3000),
      api.getTableRows(sessionId, 'users', 2000),
      api.getTableRows(sessionId, 'worlds', 300),
      api.getTableRows(sessionId, 'character_locations', 3000),
    ]);

    allCharacters = rowsToObjects(charactersResponse.columns, charactersResponse.rows).filter(
      (character) => !isTombstonedCharacter(character)
    );

    const users = rowsToObjects(usersResponse.columns, usersResponse.rows);
    userById = new Map(users.map((user) => [Number(user.id), user]));

    const worlds = rowsToObjects(worldsResponse.columns, worldsResponse.rows);
    worldNameById = new Map(worlds.map((world) => [String(world.id), String(world.name)]));

    const locations = rowsToObjects(locationsResponse.columns, locationsResponse.rows);
    locationByCharacterId = new Map(
      locations.map((location) => [Number(location.character_id), location])
    );
  };

  /**
   * Ensure axis state/event data is loaded for one character.
   *
   * @param {number|null} characterId
   */
  const ensureAxisData = async (characterId) => {
    if (!characterId || axisStateByCharacter.has(characterId) || axisLoadingCharacterIds.has(characterId)) {
      return;
    }

    axisLoadingCharacterIds.add(characterId);
    axisErrorByCharacter.delete(characterId);
    try {
      const [axisStateResponse, axisEventsResponse] = await Promise.all([
        api.getCharacterAxisState(sessionId, characterId),
        api.getCharacterAxisEvents(sessionId, characterId, 25),
      ]);
      axisStateByCharacter.set(characterId, axisStateResponse);
      axisEventsByCharacter.set(characterId, axisEventsResponse.events || []);
    } catch (error) {
      axisErrorByCharacter.set(
        characterId,
        error instanceof Error ? error.message : 'Unable to load axis data.'
      );
    } finally {
      axisLoadingCharacterIds.delete(characterId);
      render();
    }
  };

  const render = () => {
    const filteredCharacters = allCharacters
      .filter((character) => {
        const worldId = String(character.world_id || '');
        if (worldFilter !== 'all' && worldId !== worldFilter) {
          return false;
        }

        const owner = userById.get(Number(character.user_id));
        const haystack = [character.name, owner?.username, worldId].filter(Boolean).join(' ').toLowerCase();
        return haystack.includes(searchTerm.trim().toLowerCase());
      })
      .sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));

    if (!filteredCharacters.length) {
      selectedCharacterId = null;
    } else if (!filteredCharacters.some((character) => Number(character.id) === selectedCharacterId)) {
      selectedCharacterId = Number(filteredCharacters[0].id);
    }

    const selectedCharacter =
      filteredCharacters.find((character) => Number(character.id) === selectedCharacterId) || null;

    const worldIds = [...new Set(allCharacters.map((character) => String(character.world_id || '')))]
      .filter(Boolean)
      .sort();

    const axisState =
      selectedCharacterId !== null ? axisStateByCharacter.get(Number(selectedCharacterId)) || null : null;
    const axisEvents =
      selectedCharacterId !== null ? axisEventsByCharacter.get(Number(selectedCharacterId)) || null : null;
    const axisLoading =
      selectedCharacterId !== null && axisLoadingCharacterIds.has(Number(selectedCharacterId));
    const axisError =
      selectedCharacterId !== null ? axisErrorByCharacter.get(Number(selectedCharacterId)) || null : null;

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Character Dashboard</h2>
            <p class="u-muted">${filteredCharacters.length} of ${allCharacters.length} characters shown.</p>
          </div>
          <div class="actions">
            <button class="btn btn--secondary" type="button" data-characters-refresh>Refresh</button>
          </div>
        </div>
        <div class="split-layout dashboard-split">
          <div class="dashboard-left">
            <div class="card table-card dashboard-table-card">
              <h3>Character Registry</h3>
              <div class="table-toolbar dashboard-toolbar">
                <label class="table-search">
                  <span>Search</span>
                  <input
                    class="input"
                    type="search"
                    placeholder="character, owner, world"
                    value="${escapeHtml(searchTerm)}"
                    data-characters-search
                  />
                </label>
                <label class="detail-form dashboard-select-inline">
                  World
                  <select class="select" data-characters-world>
                    <option value="all" ${worldFilter === 'all' ? 'selected' : ''}>All</option>
                    ${worldIds
                      .map((worldId) => {
                        const worldName = worldNameById.get(worldId) || worldId;
                        return `
                          <option value="${escapeHtml(worldId)}" ${
                            worldFilter === worldId ? 'selected' : ''
                          }>
                            ${escapeHtml(worldName)}
                          </option>
                        `;
                      })
                      .join('')}
                  </select>
                </label>
              </div>
              ${buildCharactersTable(
                filteredCharacters,
                selectedCharacterId,
                userById,
                worldNameById,
                locationByCharacterId
              )}
            </div>
          </div>
          <aside class="detail-panel dashboard-right">
            ${buildCharacterDetails(
              selectedCharacter,
              userById,
              worldNameById,
              locationByCharacterId,
              axisState,
              axisEvents,
              axisLoading,
              axisError
            )}
          </aside>
        </div>
      </div>
    `;

    const searchInput = root.querySelector('[data-characters-search]');
    if (searchInput) {
      searchInput.addEventListener('input', (event) => {
        searchTerm = event.target.value;
        render();
      });
    }

    const worldSelect = root.querySelector('[data-characters-world]');
    if (worldSelect) {
      worldSelect.addEventListener('change', (event) => {
        worldFilter = event.target.value;
        render();
      });
    }

    root.querySelectorAll('[data-character-id]').forEach((row) => {
      row.addEventListener('click', () => {
        selectedCharacterId = Number(row.getAttribute('data-character-id'));
        render();
      });
    });

    const refreshButton = root.querySelector('[data-characters-refresh]');
    if (refreshButton) {
      refreshButton.addEventListener('click', async () => {
        try {
          await load();
          render();
          showToast('Character dashboard refreshed.', 'success');
        } catch (error) {
          showToast(
            error instanceof Error ? error.message : 'Failed to refresh character dashboard.',
            'error'
          );
        }
      });
    }

    if (selectedCharacterId !== null) {
      ensureAxisData(Number(selectedCharacterId));
    }
  };

  try {
    await load();
    render();
  } catch (error) {
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Characters</h1>
        <p class="error">${
          error instanceof Error ? escapeHtml(error.message) : 'Failed to load character dashboard.'
        }</p>
      </div>
    `;
  }
}

export { renderCharactersDashboard };
