/*
 * locations.js
 *
 * Admin locations view. Lists character locations with zone info.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

async function renderLocations(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Locations</h1>
      <p class="u-muted">Loading locations...</p>
    </div>
  `;

  try {
    const response = await api.getLocations(session.session_id);
    const headers = ['Character', 'World', 'Room', 'Zone'];
    const rows = response.locations.map((entry) => [
      entry.character_name || 'Unknown',
      entry.world_id || '—',
      entry.room_id || '—',
      entry.zone_id || '—',
    ]);

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Locations</h2>
            <p class="u-muted">${rows.length} entries found.</p>
          </div>
        </div>
        <div class="card table-card">
          ${renderTable(headers, rows)}
        </div>
      </div>
    `;
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to load locations.', 'error');
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Locations</h1>
        <p class="error">Failed to load locations.</p>
      </div>
    `;
  }
}

export { renderLocations };
