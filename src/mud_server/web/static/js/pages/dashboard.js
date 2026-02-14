/*
 * dashboard.js
 *
 * Placeholder dashboard view shown after login. The real implementation
 * will pull data from admin endpoints.
 */

/**
 * Render the dashboard view.
 *
 * @param {HTMLElement} root
 * @param {object} session
 */
function renderDashboard(root, session) {
  root.innerHTML = `
    <div class="panel">
      <h1>Admin Dashboard</h1>
      <p class="muted">Logged in as ${session.role || 'unknown'}.</p>
      <p>Dashboard widgets will appear here.</p>
    </div>
  `;
}

export { renderDashboard };
