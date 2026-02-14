/*
 * pipeworks_web world script.
 *
 * This module is loaded only when the play shell is routed to
 * /play/pipeworks_web. Use it to attach UI behavior and API calls
 * specific to the PipeWorks web world.
 */

(function initPipeworksWeb() {
  const container = document.getElementById('play-content');
  if (!container) {
    return;
  }

  // Placeholder content. Replace with the real gameplay UI.
  const existing = container.querySelector('[data-world-placeholder]');
  if (existing) {
    return;
  }

  const panel = document.createElement('div');
  panel.setAttribute('data-world-placeholder', 'true');
  panel.innerHTML = `
    <h2>PipeWorks Web</h2>
    <p>World-specific UI goes here.</p>
  `;
  container.appendChild(panel);
})();
