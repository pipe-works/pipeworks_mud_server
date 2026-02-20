/*
 * sessions.js
 *
 * Admin sessions view. Lists active sessions and allows kicking.
 */

import { renderTable } from '../ui/table.js';
import { showToast } from '../ui/toasts.js';

function buildKickButton(sessionId) {
  return `
    <button class="btn btn--secondary btn--sm" data-action="kick" data-session="${sessionId}">Kick</button>
  `;
}

async function renderSessions(root, { api, session }) {
  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Sessions</h1>
      <p class="u-muted">Loading sessions...</p>
    </div>
  `;

  const sessionId = session.session_id;

  async function load() {
    const response = await api.getSessions(sessionId);
    const headers = ['Session', 'User', 'Character', 'World', 'Actions'];
    const rows = response.sessions.map((entry) => [
      entry.session_id,
      entry.username || 'Unknown',
      entry.character_name || '—',
      entry.world_id || '—',
      buildKickButton(entry.session_id),
    ]);

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Sessions</h2>
            <p class="u-muted">${rows.length} sessions found.</p>
          </div>
        </div>
        <div class="card table-card">
          ${renderTable(headers, rows)}
        </div>
      </div>
    `;

    root.querySelectorAll('[data-action="kick"]').forEach((button) => {
      button.addEventListener('click', async () => {
        const targetSession = button.dataset.session;
        if (!targetSession) {
          return;
        }
        const confirmed = confirm(`Kick session ${targetSession}?`);
        if (!confirmed) {
          return;
        }
        try {
          await api.kickSession(sessionId, targetSession);
          showToast('Session kicked.', 'success');
          await load();
        } catch (err) {
          showToast(err instanceof Error ? err.message : 'Failed to kick session.', 'error');
        }
      });
    });
  }

  try {
    await load();
  } catch (err) {
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Sessions</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load sessions.'}</p>
      </div>
    `;
  }
}

export { renderSessions };
