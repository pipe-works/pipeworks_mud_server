/*
 * play.js
 *
 * Base bootstrap for the play shell.
 *
 * The shell intentionally separates:
 * 1) Account login session
 * 2) Character selection for a specific world
 * 3) In-world gameplay state
 *
 * World-specific scripts can extend this behavior when /play/<world_id> is used.
 */

import {
  createCharacter,
  getErrorMessage,
  getStatus,
  login,
  logout,
  selectCharacter,
} from './play_api.js';
import {
  clearSession,
  consumeFlashMessage,
  readSession,
  updateSession,
  writeFlashMessage,
  writeSession,
} from './play_session.js';
import { startGameSession, stopChatPolling } from './play_game_session.js';
import {
  setLogoutButtonVisible,
  setState,
  updateCharacterName,
  updateLocation,
  updateStatus,
} from './play_dom.js';
import {
  getDefaultWorldId,
  getSelectedCharacterId,
  getSelectedWorldId,
  getSelectedWorldOption,
  getWorldId,
  getWorldOptions,
  getPreferredWorldId,
  populateWorldSelect,
  refreshCharactersForWorld,
  updateCharacterHint,
  updateCreateCharacterButtonState,
  updateEnterWorldButtonState,
  updateWorldPolicyHint,
} from './play_portal.js';

/**
 * Authenticate account credentials and transition to world/character selection.
 *
 * @returns {Promise<void>}
 */
async function handleLogin() {
  const accountInput = document.getElementById('play-account-name');
  const passwordInput = document.getElementById('play-password');
  const accountUsername = accountInput?.value?.trim() || '';
  const password = passwordInput?.value?.trim() || '';

  if (!accountUsername || !password) {
    throw new Error('Username and password are required.');
  }

  updateStatus('Logging in...');

  const loginResponse = await login({
    username: accountUsername,
    password,
  });

  if (!loginResponse?.session_id) {
    throw new Error('Login succeeded but session id missing.');
  }

  const worldOptions = getWorldOptions(loginResponse.available_worlds);
  const preferredWorldId = getPreferredWorldId(worldOptions);
  writeSession({
    session_id: loginResponse.session_id,
    username: accountUsername,
    account_username: accountUsername,
    role: loginResponse.role || null,
    available_worlds: worldOptions,
    selected_world_id: preferredWorldId,
    selected_character_id: null,
    selected_character_name: null,
  });

  setLogoutButtonVisible(true);

  updateStatus(`Logged in as ${accountUsername}.`);
  updateCharacterName(accountUsername);
  updateLocation('Select a world and character to continue.');

  populateWorldSelect(worldOptions, preferredWorldId);
  updateWorldPolicyHint(worldOptions.find((entry) => entry.id === preferredWorldId) || null);
  await refreshCharactersForWorld({
    sessionId: loginResponse.session_id,
    worldId: preferredWorldId,
  });
  updateCreateCharacterButtonState();
  setState('select-world');
}

/**
 * End the current session and reset shell state to logged out.
 *
 * @returns {Promise<void>}
 */
async function handleLogout() {
  stopChatPolling();
  const session = readSession();
  if (!session?.session_id) {
    clearSession();
    setState('logged-out');
    return;
  }

  updateStatus('Logging out...');
  await logout(session.session_id);
  clearSession();
  setState('logged-out');
  updateStatus('Ready to issue a visitor account.');
  updateLocation('Logged out.');
  updateCharacterHint('Select a world to load available characters.');
  updateWorldPolicyHint(null);
  updateCharacterName('Character Name');
  setLogoutButtonVisible(false);
  updateCreateCharacterButtonState();
}

/**
 * Wire UI events for login/logout/world entry interactions.
 *
 * @returns {void}
 */
function bindEvents() {
  const loginButton = document.getElementById('play-login-button');
  const logoutButton = document.getElementById('play-logout-button');
  const enterWorldButton = document.getElementById('play-enter-world');
  const createCharacterButton = document.getElementById('play-create-character');
  const worldSelect = document.getElementById('play-world-select');
  const characterSelect = document.getElementById('play-character-select');

  if (loginButton) {
    loginButton.addEventListener('click', async () => {
      loginButton.disabled = true;
      try {
        await handleLogin();
      } catch (err) {
        updateStatus(`Goblin says: ${getErrorMessage(err)}`);
      } finally {
        loginButton.disabled = false;
      }
    });
  }

  if (logoutButton) {
    logoutButton.addEventListener('click', async () => {
      logoutButton.disabled = true;
      try {
        await handleLogout();
      } catch (err) {
        updateStatus(`Goblin says: ${getErrorMessage(err)}`);
      } finally {
        logoutButton.disabled = false;
      }
    });
  }

  if (worldSelect) {
    worldSelect.addEventListener('change', async () => {
      const session = readSession();
      if (!session?.session_id) {
        return;
      }

      const selectedWorld = getSelectedWorldId();
      const worldOption = getSelectedWorldOption();
      updateSession({
        selected_world_id: selectedWorld,
        selected_character_id: null,
        selected_character_name: null,
      });
      updateWorldPolicyHint(worldOption);

      try {
        await refreshCharactersForWorld({
          sessionId: session.session_id,
          worldId: selectedWorld,
        });
      } catch (err) {
        updateCharacterHint(getErrorMessage(err));
        updateEnterWorldButtonState();
        updateCreateCharacterButtonState();
      }
    });
  }

  if (characterSelect) {
    characterSelect.addEventListener('change', () => {
      const selectedCharacterId = getSelectedCharacterId();
      const selectedCharacterName = characterSelect.selectedOptions?.[0]?.textContent || null;
      updateSession({
        selected_character_id: selectedCharacterId,
        selected_character_name: selectedCharacterName,
      });
      updateEnterWorldButtonState();
      updateCreateCharacterButtonState();
    });
  }

  if (createCharacterButton) {
    createCharacterButton.addEventListener('click', async () => {
      const session = readSession();
      if (!session?.session_id) {
        updateStatus('Session unavailable. Please log in again.');
        setState('logged-out');
        return;
      }

      const selectedWorld = getSelectedWorldId();
      const worldOption = getSelectedWorldOption();
      if (!worldOption || worldOption.can_access === false) {
        updateCharacterHint('This world is invite-locked for your account.');
        updateCreateCharacterButtonState();
        return;
      }

      createCharacterButton.disabled = true;
      updateCharacterHint(`Generating a character for ${selectedWorld}...`);
      try {
        const created = await createCharacter(session.session_id, selectedWorld);
        await refreshCharactersForWorld({
          sessionId: session.session_id,
          worldId: selectedWorld,
          preferredCharacterId: created?.character_id || null,
        });
        updateStatus(`Character ${created?.character_name || 'created'} is ready.`);
        updateCharacterHint(
          `Character ${created?.character_name || 'created'} is available. Select it to enter.`
        );
      } catch (err) {
        updateStatus(`Goblin says: ${getErrorMessage(err)}`);
        updateCharacterHint(getErrorMessage(err));
      } finally {
        createCharacterButton.disabled = false;
        updateCreateCharacterButtonState();
      }
    });
  }

  if (enterWorldButton) {
    enterWorldButton.addEventListener('click', async () => {
      const session = readSession();
      if (!session?.session_id) {
        updateStatus('Session unavailable. Please log in again.');
        setState('logged-out');
        return;
      }

      const selectedWorld = getSelectedWorldId();
      const selectedCharacterId = getSelectedCharacterId();
      if (!selectedCharacterId) {
        updateCharacterHint('Select a character before entering the world.');
        updateEnterWorldButtonState();
        return;
      }

      enterWorldButton.disabled = true;
      try {
        const selection = await selectCharacter(
          session.session_id,
          selectedCharacterId,
          selectedWorld
        );
        const selectedCharacterName = selection?.character_name || 'Character';
        updateSession({
          selected_world_id: selectedWorld,
          selected_character_id: selectedCharacterId,
          selected_character_name: selectedCharacterName,
        });

        updateStatus(`Entering ${selectedWorld} as ${selectedCharacterName}...`);
        updateCharacterName(selectedCharacterName);
        window.location.assign(`/play/${selectedWorld}`);
      } catch (err) {
        updateStatus(`Goblin says: ${getErrorMessage(err)}`);
      } finally {
        enterWorldButton.disabled = false;
      }
    });
  }
}

/**
 * Restore account session for `/play` and repopulate world/character selectors.
 *
 * @returns {Promise<void>}
 */
async function hydratePortalSession() {
  const session = readSession();
  if (!session?.session_id) {
    const flashMessage = consumeFlashMessage();
    setState('logged-out');
    if (flashMessage) {
      updateStatus(flashMessage);
    }
    return;
  }

  setLogoutButtonVisible(true);

  updateStatus('Checking existing account session...');
  updateCharacterName(session.selected_character_name || session.username || 'Character Name');
  updateLocation('Select a world and character to continue.');

  const worldOptions = getWorldOptions(session.available_worlds);
  const storedWorldId = typeof session.selected_world_id === 'string' ? session.selected_world_id : '';
  const preferredWorldId = getPreferredWorldId(worldOptions, storedWorldId);
  updateSession({ selected_world_id: preferredWorldId });
  populateWorldSelect(worldOptions, preferredWorldId);
  updateWorldPolicyHint(worldOptions.find((entry) => entry.id === preferredWorldId) || null);
  setState('select-world');

  const flashMessage = consumeFlashMessage();
  if (flashMessage) {
    updateStatus(flashMessage);
  }

  try {
    await refreshCharactersForWorld({
      sessionId: session.session_id,
      worldId: preferredWorldId,
      preferredCharacterId: session.selected_character_id || null,
    });
    updateStatus('Session active. Choose a world and character to continue.');
    updateCreateCharacterButtonState();
  } catch (err) {
    clearSession();
    setState('logged-out');
    updateStatus(`Session expired. ${getErrorMessage(err)}`);
  }
}

/**
 * Ensure world routes only render when a character-bound session is valid.
 *
 * @param {string} worldId
 * @returns {Promise<void>}
 */
async function hydrateWorldSession(worldId) {
  const session = readSession();
  if (!session?.session_id) {
    writeFlashMessage('Log in and select a character before entering a world.');
    window.location.assign('/play');
    return;
  }

  const selectedWorldId = session.selected_world_id || '';
  if (selectedWorldId && selectedWorldId !== worldId) {
    window.location.assign(`/play/${selectedWorldId}`);
    return;
  }

  updateStatus('Validating in-world session...');
  try {
    await getStatus(session.session_id);
    setState('in-world');
    updateCharacterName(session.selected_character_name || session.username || 'Character Name');
    updateLocation(`Entering ${worldId}...`);
    setLogoutButtonVisible(true);
    await startGameSession(worldId, session.session_id);
  } catch (err) {
    writeFlashMessage(
      `Unable to enter ${worldId}: ${getErrorMessage(err)} Select a character and try again.`
    );
    window.location.assign('/play');
  }
}

/**
 * Bootstrap the play shell based on current route context.
 *
 * @returns {Promise<void>}
 */
async function initPlayShell() {
  const worldId = getWorldId();
  bindEvents();

  if (worldId) {
    await hydrateWorldSession(worldId);
    return;
  }

  await hydratePortalSession();
}

initPlayShell().catch((err) => {
  clearSession();
  setState('logged-out');
  updateStatus(`Goblin says: ${getErrorMessage(err)}`);
});
