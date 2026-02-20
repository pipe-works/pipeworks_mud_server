/*
 * tables.js
 *
 * Admin tables view. Lists tables and allows viewing row samples.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

async function renderTables(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Tables</h1>
      <p class="u-muted">Loading tables...</p>
    </div>
  `;

  try {
    const response = await api.getTables(session.session_id);
    const headers = ['Table', 'Columns'];
    const rows = response.tables.map((table) => {
      // Support both string and object column formats for safety.
      const columns = (table.columns || []).map((col) =>
        typeof col === 'string' ? col : col?.name || ''
      );
      return [table.name, columns.filter((col) => col).join(', ')];
    });

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Tables</h2>
            <p class="u-muted">${rows.length} tables found.</p>
          </div>
        </div>
        <div class="card table-card">
          ${renderTable(headers, rows)}
        </div>
      </div>
    `;
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to load tables.', 'error');
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Tables</h1>
        <p class="error">Failed to load tables.</p>
      </div>
    `;
  }
}

export { renderTables };
