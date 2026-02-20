/*
 * chat.js
 *
 * Admin chat view. Lists recent chat messages.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

async function renderChat(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Chat</h1>
      <p class="u-muted">Loading chat messages...</p>
    </div>
  `;

  try {
    const response = await api.getChatMessages(session.session_id, 100);
    const headers = ['User', 'World', 'Room', 'Message'];
    const rows = response.messages.map((entry) => [
      entry.username || 'Unknown',
      entry.world_id || '—',
      entry.room_id || '—',
      entry.message || '',
    ]);

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Chat</h2>
            <p class="u-muted">${rows.length} messages loaded.</p>
          </div>
        </div>
        <div class="card table-card">
          ${renderTable(headers, rows)}
        </div>
      </div>
    `;
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to load chat.', 'error');
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Chat</h1>
        <p class="error">Failed to load chat.</p>
      </div>
    `;
  }
}

export { renderChat };
