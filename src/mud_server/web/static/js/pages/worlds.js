/*
 * worlds.js
 *
 * Admin worlds view. Lists worlds from the worlds table.
 */

import { renderTable } from '../ui/table.js';

async function renderWorlds(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Worlds</h1>
      <p class="muted">Loading worlds...</p>
    </div>
  `;

  try {
    const response = await api.getTableRows(session.session_id, 'worlds', 200);
    const headers = response.columns.map((col) =>
      typeof col === 'string' ? col : col.name
    );
    const rows = response.rows.map((row) => headers.map((col) => `${row[col] ?? ''}`));

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Worlds</h2>
            <p class="muted">${rows.length} worlds found.</p>
          </div>
        </div>
        <div class="card table-card">
          ${renderTable(headers, rows)}
        </div>
      </div>
    `;
  } catch (err) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Worlds</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load worlds.'}</p>
      </div>
    `;
  }
}

export { renderWorlds };
