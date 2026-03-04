/*
 * play_dom.js
 *
 * DOM state and text helpers for the play shell.
 */

/**
 * Collect top-level UI containers for state toggling.
 *
 * @returns {{loggedOut: HTMLElement|null, selectWorld: HTMLElement|null, inWorld: HTMLElement|null}}
 */
function getStateElements() {
  return {
    loggedOut: document.querySelector('[data-play-state="logged-out"]'),
    selectWorld: document.querySelector('[data-play-state="select-world"]'),
    inWorld: document.querySelector('[data-play-state="in-world"]'),
  };
}

/**
 * Toggle the shell state panels.
 *
 * @param {'logged-out'|'select-world'|'in-world'} state
 * @returns {void}
 */
function setState(state) {
  const { loggedOut, selectWorld, inWorld } = getStateElements();
  if (loggedOut) {
    loggedOut.hidden = state !== 'logged-out';
  }
  if (selectWorld) {
    selectWorld.hidden = state !== 'select-world';
  }
  if (inWorld) {
    inWorld.hidden = state !== 'in-world';
  }
}

/**
 * Update top-level status text.
 *
 * @param {string} message
 * @returns {void}
 */
function updateStatus(message) {
  const status = document.getElementById('play-status');
  if (status) {
    status.textContent = message;
  }
}

/**
 * Update the in-world character name label.
 *
 * @param {string} name
 * @returns {void}
 */
function updateCharacterName(name) {
  const label = document.getElementById('play-character-name-display');
  if (label) {
    label.textContent = name;
  }
}

/**
 * Update location message in the in-world panel.
 *
 * @param {string} message
 * @returns {void}
 */
function updateLocation(message) {
  const element = document.getElementById('play-location');
  if (element) {
    element.textContent = message;
  }
}

/**
 * Show or hide the shared logout button.
 *
 * @param {boolean} isVisible
 * @returns {void}
 */
function setLogoutButtonVisible(isVisible) {
  const logoutButton = document.getElementById('play-logout-button');
  if (logoutButton) {
    logoutButton.hidden = !isVisible;
  }
}

export {
  getStateElements,
  setLogoutButtonVisible,
  setState,
  updateCharacterName,
  updateLocation,
  updateStatus,
};
