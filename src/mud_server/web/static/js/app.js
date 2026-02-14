/*
 * Minimal bootstrap for the admin dashboard.
 *
 * This file will grow as we add routing and pages. For now it simply
 * confirms that the UI shell loaded and the JS pipeline is working.
 */

(() => {
  'use strict';

  const root = document.getElementById('app');
  if (!root) {
    return;
  }

  root.innerHTML = `
    <div class="app-loading">
      Admin dashboard assets loaded. UI build in progress.
    </div>
  `;
})();
