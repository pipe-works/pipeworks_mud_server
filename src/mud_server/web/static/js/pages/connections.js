/*
 * connections.js
 *
 * Admin connections view. Lists active connections.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

async function renderConnections(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Connections</h1>
      <p class="u-muted">Loading connections...</p>
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
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Connections</h2>
            <p class="u-muted">${rows.length} connections found.</p>
          </div>
        </div>
        <div class="card table-card">
          ${renderTable(headers, rows)}
        </div>
      </div>
    `;
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to load connections.', 'error');
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Connections</h1>
        <p class="error">Failed to load connections.</p>
      </div>
    `;
  }
}

export { renderConnections };
