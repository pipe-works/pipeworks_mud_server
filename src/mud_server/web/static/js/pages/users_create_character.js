/*
 * users_create_character.js
 *
 * Focused helpers for the "Create Character" tab in the admin Users detail
 * card. This module keeps provisioning-specific rendering and event wiring
 * isolated from the main users page controller.
 */

/**
 * Escape plain text for safe HTML insertion.
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
 * Build the world selector options for the create-character form.
 *
 * @param {Array<{id: string, name: string}>} worlds
 * @param {string} selectedWorldId
 * @returns {string}
 */
function buildWorldOptions(worlds, selectedWorldId) {
  return worlds
    .map((world) => {
      const worldId = String(world.id);
      const worldName = world.name || world.id;
      const selected = worldId === selectedWorldId ? 'selected' : '';
      return `<option value="${escapeHtml(worldId)}" ${selected}>${escapeHtml(worldName)}</option>`;
    })
    .join('');
}

/**
 * Render the Create Character tab panel.
 *
 * @param {object} params
 * @param {{id:number, username:string}|null} params.user
 * @param {Array<{id: string, name: string}>} params.worlds
 * @param {string} params.selectedWorldId
 * @param {boolean} params.isSubmitting
 * @returns {string}
 */
function buildCreateCharacterPanel({ user, worlds, selectedWorldId, isSubmitting }) {
  if (!user) {
    return '<p class="muted">Select a user to provision a character.</p>';
  }

  if (!worlds.length) {
    return '<p class="muted">No active worlds available for character provisioning.</p>';
  }

  return `
    <div class="create-character-panel">
      <p class="detail-help">
        A name is minted via the name-generation API, then character and
        occupation axis conditions are seeded from the entity-state API using
        one replayable seed.
      </p>
      <form class="detail-form" data-create-character-form>
        <label>
          Account
          <input type="text" value="${escapeHtml(user.username)}" readonly />
        </label>
        <label>
          World
          <select name="world_id" data-create-character-world required>
            ${buildWorldOptions(worlds, selectedWorldId)}
          </select>
        </label>
        <button type="submit" ${isSubmitting ? 'disabled' : ''}>
          ${isSubmitting ? 'Creating...' : 'Create character'}
        </button>
      </form>
      <p class="muted detail-help">
        If generated names collide with existing characters, the server retries
        with nearby seeds before returning an error.
      </p>
    </div>
  `;
}

/**
 * Bind Create Character tab interactions.
 *
 * @param {object} params
 * @param {HTMLElement} params.root
 * @param {object} params.api
 * @param {string} params.sessionId
 * @param {{username:string}|null} params.user
 * @param {string} params.selectedWorldId
 * @param {(value: string) => void} params.setSelectedWorldId
 * @param {(value: boolean) => void} params.setIsSubmitting
 * @param {(response: any) => Promise<void>} params.onSuccess
 * @param {(error: any) => void} params.onError
 */
function bindCreateCharacterPanel({
  root,
  api,
  sessionId,
  user,
  selectedWorldId,
  setSelectedWorldId,
  setIsSubmitting,
  onSuccess,
  onError,
}) {
  const form = root.querySelector('[data-create-character-form]');
  if (!form || !user) {
    return;
  }

  const worldSelect = root.querySelector('[data-create-character-world]');
  if (worldSelect) {
    worldSelect.addEventListener('change', (event) => {
      setSelectedWorldId(event.target.value);
    });
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const worldId = (worldSelect?.value || selectedWorldId || '').trim();
    if (!worldId) {
      onError(new Error('World is required.'));
      return;
    }
    if (typeof api.createCharacter !== 'function') {
      onError(
        new Error(
          'Admin UI assets are out of sync. Hard refresh the page (disable cache) and try again.'
        )
      );
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await api.createCharacter({
        session_id: sessionId,
        target_username: user.username,
        world_id: worldId,
      });
      await onSuccess(response);
    } catch (error) {
      onError(error);
    } finally {
      setIsSubmitting(false);
    }
  });
}

export { bindCreateCharacterPanel, buildCreateCharacterPanel };
