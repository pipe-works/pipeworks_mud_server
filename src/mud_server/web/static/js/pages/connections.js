/*
 * connections.js
 *
 * Admin connections view. Lists active connections.
 */

import { renderTable } from '../ui/table.js';

async function renderConnections(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Connections</h1>
      <p class="muted">Loading connections...</p>
    </div>
  `;

  try {
    const response = await api.getConnections(session.session_id);
    const headers = ['Session', 'Username', 'Client', 'Last Seen'];
    const rows = response.connections.map((entry) => [
      entry.session_id,
      entry.username || 'Unknown',
      entry.client_type || 'unknown',
      entry.last_seen || '—',
    ]);

    root.innerHTML = `
      <div class="panel wide">
        <h1>Connections</h1>
        <p class="muted">${rows.length} connections found.</p>
        ${renderTable(headers, rows)}
      </div>
    `;
  } catch (err) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Connections</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load connections.'}</p>
      </div>
    `;
  }
}

export { renderConnections };
