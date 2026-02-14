/*
 * play.js
 *
 * Base bootstrap for the play shell. It reads the world id from the
 * data-world-id attribute and provides a minimal placeholder UI.
 *
 * World-specific modules can override or extend this behavior by
 * loading /web/static/play/js/worlds/<world_id>.js.
 */

function getWorldId() {
  const root = document.body;
  return root?.dataset?.worldId || '';
}

function renderPlaceholder(worldId) {
  const container = document.getElementById('play-content');
  if (!container) {
    return;
  }

  if (!worldId) {
    container.innerHTML = `
      <div>
        <h2>Choose a world</h2>
        <p>
          No world selected. Visit a world-specific URL such as
          <code>/play/pipeworks_web</code>.
        </p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div>
      <h2>World: ${worldId}</h2>
      <p>This shell is ready for the world-specific UI.</p>
    </div>
  `;
}

(function initPlayShell() {
  const worldId = getWorldId();
  renderPlaceholder(worldId);
})();
