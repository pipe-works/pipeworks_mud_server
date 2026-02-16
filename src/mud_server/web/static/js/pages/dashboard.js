/*
 * dashboard.js
 *
 * Dashboard view rendering simple admin metrics.
 */

async function renderDashboard(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Admin Dashboard</h1>
      <p class="muted">Loading summary...</p>
    </div>
  `;

  try {
    const sessionId = session.session_id;
    const [players, sessions, connections, worlds] = await Promise.all([
      api.getPlayers(sessionId),
      api.getSessions(sessionId),
      api.getConnections(sessionId),
      api.getTableRows(sessionId, 'worlds', 200),
    ]);

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Admin Overview</h2>
            <p class="muted">Snapshot of active users, sessions, and worlds.</p>
          </div>
        </div>
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="stat-label">Users</div>
            <div class="stat-value">${players.players.length}</div>
          </div>
          <div class="kpi-card">
            <div class="stat-label">Sessions</div>
            <div class="stat-value">${sessions.sessions.length}</div>
          </div>
          <div class="kpi-card">
            <div class="stat-label">Connections</div>
            <div class="stat-value">${connections.connections.length}</div>
          </div>
          <div class="kpi-card">
            <div class="stat-label">Worlds</div>
            <div class="stat-value">${worlds.rows.length}</div>
          </div>
        </div>
        <div class="card">
          <h3>Quick Actions</h3>
          <p class="muted">Jump straight to high-impact views.</p>
          <div class="actions">
            <a href="/admin/users">Manage users</a>
            <a href="/admin/accounts">Account dashboard</a>
            <a href="/admin/characters">Character dashboard</a>
            <a href="/admin/tombstones">Tombstone dashboard</a>
            <a href="/admin/sessions">Active sessions</a>
            <a href="/admin/tables">Database tables</a>
          </div>
        </div>
      </div>
    `;
  } catch (err) {
    root.innerHTML = `
      <div class="panel wide">
        <h1>Admin Dashboard</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load data.'}</p>
      </div>
    `;
  }
}

export { renderDashboard };
