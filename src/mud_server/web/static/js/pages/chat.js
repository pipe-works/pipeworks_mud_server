/*
 * chat.js
 *
 * Admin chat view. Lists recent chat messages.
 */

import { renderTable } from '../ui/table.js';

async function renderChat(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Chat</h1>
      <p class="muted">Loading chat messages...</p>
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
      <div class="panel wide">
        <h1>Chat</h1>
        <p class="muted">${rows.length} messages loaded.</p>
        ${renderTable(headers, rows)}
      </div>
    `;
  } catch (err) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Chat</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load chat.'}</p>
      </div>
    `;
  }
}

export { renderChat };
