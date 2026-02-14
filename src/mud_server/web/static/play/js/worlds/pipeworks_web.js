/*
 * pipeworks_web.js
 *
 * World-specific behaviors for the PipeWorks web world. This file is currently
 * a placeholder and is meant to be extended with actual gameplay bindings.
 */

(function initPipeworksWeb() {
  const output = document.getElementById('gameOutput');
  if (!output) {
    return;
  }

  const entry = document.createElement('div');
  entry.className = 'output-text';
  entry.textContent = 'PipeWorks Web world loaded. Awaiting commands.';
  output.appendChild(entry);
})();
