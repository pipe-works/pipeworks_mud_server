/*
 * superuser.js
 *
 * Superuser-only panel. Includes server stop and export shortcuts.
 */

function renderSuperuser(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Superuser</h1>
      <p class="muted">Danger zone actions for superusers.</p>
      <div class="actions">
        <button data-action="stop">Stop server</button>
        <button data-action="export">Export worlds table (JSON)</button>
      </div>
    </div>
  `;

  const stopButton = root.querySelector('[data-action="stop"]');
  stopButton.addEventListener('click', async () => {
    const confirmed = confirm('Stop the server? This will terminate the process.');
    if (!confirmed) {
      return;
    }
    try {
      await api.stopServer(session.session_id);
      alert('Server stop requested.');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to stop server.');
    }
  });

  const exportButton = root.querySelector('[data-action="export"]');
  exportButton.addEventListener('click', async () => {
    try {
      const data = await api.getTableRows(session.session_id, 'worlds', 200);
      const blob = new Blob([JSON.stringify(data.rows, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'worlds.json';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to export worlds.');
    }
  });
}

export { renderSuperuser };
