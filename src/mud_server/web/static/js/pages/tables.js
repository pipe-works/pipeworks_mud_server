/*
 * tables.js
 *
 * Admin tables view. Lists tables and allows viewing row samples.
 */

import { renderTable } from '../ui/table.js';

async function renderTables(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Tables</h1>
      <p class="muted">Loading tables...</p>
    </div>
  `;

  try {
    const response = await api.getTables(session.session_id);
    const headers = ['Table', 'Columns'];
    const rows = response.tables.map((table) => [
      table.name,
      (table.columns || []).map((col) => col.name).join(', '),
    ]);

    root.innerHTML = `
      <div class="panel wide">
        <h1>Tables</h1>
        <p class="muted">${rows.length} tables found.</p>
        ${renderTable(headers, rows)}
      </div>
    `;
  } catch (err) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Tables</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load tables.'}</p>
      </div>
    `;
  }
}

export { renderTables };
