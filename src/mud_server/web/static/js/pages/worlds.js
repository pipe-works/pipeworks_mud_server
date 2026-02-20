/*
 * worlds.js
 *
 * Admin worlds operations view.
 *
 * This page is intentionally separate from generic table browsing so admins
 * and superusers can inspect per-world online state and moderate active
 * characters directly from one place.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

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

function formatTimestamp(value) {
  if (!value) {
    return '—';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString();
}

function buildStatusPill(label, isOnline) {
  return `<span class="badge ${isOnline ? 'badge--active' : 'badge--muted'}">${escapeHtml(label)}</span>`;
}

function buildKickButton(characterId, characterName) {
  return `
    <button
      class="btn btn--secondary btn--sm"
      data-kick-character="${characterId}"
      data-kick-name="${escapeHtml(characterName)}"
    >
      Kick
    </button>
  `;
}

function flattenActiveCharacters(worlds) {
  const rows = [];
  worlds.forEach((world) => {
    const activeCharacters = Array.isArray(world.active_characters) ? world.active_characters : [];
    activeCharacters.forEach((entry) => {
      rows.push({
        world_id: world.world_id,
        character_id: entry.character_id,
        character_name: entry.character_name,
        username: entry.username,
        session_id: entry.session_id,
        client_type: entry.client_type,
        last_activity: entry.last_activity,
      });
    });
  });
  return rows;
}

async function renderWorlds(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Worlds</h1>
      <p class="u-muted">Loading world operations...</p>
    </div>
  `;

  const sessionId = session.session_id;
  const AUTO_REFRESH_INTERVAL_MS = 15000;
  let autoRefreshHandle = null;

  async function load() {
    const response = await api.getWorldStatus(sessionId);
    const worlds = Array.isArray(response.worlds) ? response.worlds : [];
    const worldHeaders = [
      'World ID',
      'Name',
      'Catalog Status',
      'Online Status',
      'Active Sessions',
      'Active Characters',
      'Last Activity',
    ];
    const worldRows = worlds.map((world) => [
      escapeHtml(world.world_id || ''),
      escapeHtml(world.name || world.world_id || ''),
      buildStatusPill(world.is_active ? 'Active' : 'Inactive', !!world.is_active),
      buildStatusPill(world.is_online ? 'Online' : 'Offline', !!world.is_online),
      `${world.active_session_count ?? 0}`,
      `${world.active_character_count ?? 0}`,
      formatTimestamp(world.last_activity),
    ]);

    const activeCharacters = flattenActiveCharacters(worlds);
    const characterHeaders = ['World', 'Character', 'User', 'Session', 'Client', 'Last Activity', 'Actions'];
    const characterRows = activeCharacters.map((entry) => [
      escapeHtml(entry.world_id || ''),
      escapeHtml(entry.character_name || ''),
      escapeHtml(entry.username || 'Unknown'),
      escapeHtml(entry.session_id || ''),
      escapeHtml(entry.client_type || 'unknown'),
      formatTimestamp(entry.last_activity),
      buildKickButton(entry.character_id, entry.character_name),
    ]);

    const activeCharactersHtml = characterRows.length
      ? renderTable(characterHeaders, characterRows)
      : '<p class="u-muted">No active in-world characters.</p>';

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>World Operations</h2>
            <p class="u-muted">${worldRows.length} worlds tracked · ${activeCharacters.length} active characters.</p>
          </div>
        </div>
        <div class="card table-card">
          <h3>World Status</h3>
          <p class="u-muted">Live status rows used for moderation and operational checks.</p>
          ${renderTable(worldHeaders, worldRows)}
        </div>
        <div class="card table-card">
          <h3>Active Characters</h3>
          <p class="u-muted">Kick disconnects all active sessions bound to a character.</p>
          ${activeCharactersHtml}
        </div>
      </div>
    `;

    root.querySelectorAll('[data-kick-character]').forEach((button) => {
      button.addEventListener('click', async () => {
        const characterIdRaw = button.getAttribute('data-kick-character');
        const characterName = button.getAttribute('data-kick-name') || 'character';
        const characterId = Number(characterIdRaw);
        if (!characterIdRaw || Number.isNaN(characterId) || characterId <= 0) {
          return;
        }
        if (!confirm(`Kick "${characterName}" from the world?`)) {
          return;
        }
        try {
          const result = await api.kickCharacter(sessionId, characterId);
          showToast(result.message || 'Character kicked.', 'success');
          await load();
        } catch (err) {
          showToast(err instanceof Error ? err.message : 'Failed to kick character.', 'error');
        }
      });
    });
  }

  try {
    await load();
    autoRefreshHandle = window.setInterval(async () => {
      if (!root.isConnected) {
        if (autoRefreshHandle) {
          clearInterval(autoRefreshHandle);
          autoRefreshHandle = null;
        }
        return;
      }
      if (document.hidden) {
        return;
      }
      try {
        await load();
      } catch (_err) {
        // Keep background refresh quiet; explicit user actions show toasts.
      }
    }, AUTO_REFRESH_INTERVAL_MS);
  } catch (err) {
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Worlds</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load world operations.'}</p>
      </div>
    `;
  }
}

export { renderWorlds };
