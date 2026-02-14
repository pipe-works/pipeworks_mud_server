/*
 * locations.js
 *
 * Admin locations view. Lists character locations with zone info.
 */

import { renderTable } from '../ui/table.js';

async function renderLocations(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Locations</h1>
      <p class="muted">Loading locations...</p>
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
      <div class="panel wide">
        <h1>Locations</h1>
        <p class="muted">${rows.length} entries found.</p>
        ${renderTable(headers, rows)}
      </div>
    `;
  } catch (err) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Locations</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load locations.'}</p>
      </div>
    `;
  }
}

export { renderLocations };
