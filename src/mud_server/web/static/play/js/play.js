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

const STORAGE_KEY = 'pipeworks_play_session';
const FLASH_KEY = 'pipeworks_play_flash';

/**
 * Read world id from the server-rendered body dataset.
 *
 * @returns {string}
 */
function getWorldId() {
  const root = document.body;
  return root?.dataset?.worldId || '';
}

/**
 * Return the fallback world id when the shell route is world-agnostic.
 *
 * @returns {string}
 */
function getDefaultWorldId() {
  return getWorldId() || 'pipeworks_web';
}

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
  if (loggedOut) loggedOut.hidden = state !== 'logged-out';
  if (selectWorld) selectWorld.hidden = state !== 'select-world';
  if (inWorld) inWorld.hidden = state !== 'in-world';
}

/**
 * Read account/character session payload from sessionStorage.
 *
 * @returns {Record<string, unknown>|null}
 */
function readSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return null;
  }
}

/**
 * Persist session payload for play shell flows.
 *
 * @param {Record<string, unknown>} payload
 * @returns {void}
 */
function writeSession(payload) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

/**
 * Merge session patch data into the existing payload.
 *
 * @param {Record<string, unknown>} patch
 * @returns {void}
 */
function updateSession(patch) {
  const current = readSession() || {};
  writeSession({ ...current, ...patch });
}

/**
 * Remove current session payload.
 *
 * @returns {void}
 */
function clearSession() {
  sessionStorage.removeItem(STORAGE_KEY);
}

/**
 * Persist a one-time flash message to show after navigation.
 *
 * @param {string} message
 * @returns {void}
 */
function writeFlashMessage(message) {
  sessionStorage.setItem(FLASH_KEY, message);
}

/**
 * Read and remove a one-time flash message.
 *
 * @returns {string}
 */
function consumeFlashMessage() {
  const message = sessionStorage.getItem(FLASH_KEY) || '';
  if (message) {
    sessionStorage.removeItem(FLASH_KEY);
  }
  return message;
}

/**
 * Normalize thrown values into a human-readable string.
 *
 * @param {unknown} err
 * @returns {string}
 */
function getErrorMessage(err) {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return 'Unexpected error.';
}

/**
 * Execute an API call and throw meaningful errors when the request fails.
 *
 * @param {string} endpoint
 * @param {RequestInit} options
 * @returns {Promise<any>}
 */
async function apiCall(endpoint, options) {
  const response = await fetch(endpoint, options);
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const text = await response.text();
    throw new Error(`Unexpected response (${response.status}): ${text}`);
  }
  const data = await response.json();
  if (!response.ok) {
    const message = data?.detail || data?.error || data?.message || 'Request failed.';
    const apiError = new Error(message);
    apiError.status = response.status;
    throw apiError;
  }
  return data;
}

/**
 * Authenticate an account and create an account-scoped session.
 *
 * @param {{username: string, password: string}} params
 * @returns {Promise<any>}
 */
async function login({ username, password }) {
  return apiCall('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
}

/**
 * End an existing session.
 *
 * @param {string} sessionId
 * @returns {Promise<any>}
 */
async function logout(sessionId) {
  return apiCall('/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/**
 * Fetch in-world status. This endpoint requires character selection.
 *
 * @param {string} sessionId
 * @returns {Promise<any>}
 */
async function getStatus(sessionId) {
  return apiCall(`/status/${sessionId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Fetch characters available to the session for a specific world.
 *
 * @param {string} sessionId
 * @param {string} worldId
 * @returns {Promise<any>}
 */
async function listCharacters(sessionId, worldId) {
  const params = new URLSearchParams({
    session_id: sessionId,
    world_id: worldId,
    // Hide legacy bootstrap characters in the selector when real characters exist.
    exclude_legacy_defaults: 'true',
  });
  return apiCall(`/characters?${params.toString()}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Bind a selected character to the active session for gameplay.
 *
 * @param {string} sessionId
 * @param {number} characterId
 * @param {string} worldId
 * @returns {Promise<any>}
 */
async function selectCharacter(sessionId, characterId, worldId) {
  return apiCall('/characters/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      character_id: characterId,
      world_id: worldId,
    }),
  });
}

/**
 * Provision a generated-name character for the active account session.
 *
 * @param {string} sessionId
 * @param {string} worldId
 * @returns {Promise<any>}
 */
async function createCharacter(sessionId, worldId) {
  return apiCall('/characters/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      world_id: worldId,
    }),
  });
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
 * Fill the world selector with available worlds.
 *
 * @param {Array<{id: string, name?: string, can_access?: boolean, access_mode?: string, is_locked?: boolean}>} worlds
 * @param {string} [selectedWorldId]
 * @returns {void}
 */
function populateWorldSelect(worlds, selectedWorldId = '') {
  const select = document.getElementById('play-world-select');
  if (!select) {
    return;
  }

  select.innerHTML = '';
  worlds.forEach((world) => {
    const option = document.createElement('option');
    option.value = world.id;
    const baseName = world.name || world.id;
    const modeLabel = world.access_mode === 'invite' ? 'invite' : 'open';
    const lockLabel = world.can_access === false || world.is_locked ? 'invite-locked' : modeLabel;
    option.textContent = `${baseName} (${lockLabel})`;
    option.disabled = world.can_access === false || world.is_locked === true;
    option.selected = Boolean(selectedWorldId && world.id === selectedWorldId);
    select.appendChild(option);
  });
}

/**
 * Fill the character selector for the currently selected world.
 *
 * @param {Array<{id: number, name: string}>} characters
 * @param {number|null} [selectedCharacterId]
 * @returns {void}
 */
function populateCharacterSelect(characters, selectedCharacterId = null) {
  const select = document.getElementById('play-character-select');
  if (!select) {
    return;
  }

  select.innerHTML = '';
  if (!characters.length) {
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'No characters available in this world';
    placeholder.selected = true;
    select.appendChild(placeholder);
    return;
  }

  const fallbackId = selectedCharacterId || characters[0].id;
  characters.forEach((character) => {
    const option = document.createElement('option');
    option.value = String(character.id);
    option.textContent = character.name;
    option.selected = Number(character.id) === Number(fallbackId);
    select.appendChild(option);
  });
}

/**
 * Update character helper text beneath the world/character selectors.
 *
 * @param {string} message
 * @returns {void}
 */
function updateCharacterHint(message) {
  const hint = document.getElementById('play-character-hint');
  if (hint) {
    hint.textContent = message;
  }
}

/**
 * Update per-world policy hint text in the account dashboard.
 *
 * @param {{access_mode?: string, can_access?: boolean, naming_mode?: string, slot_limit_per_account?: number, current_character_count?: number}|null} worldOption
 * @returns {void}
 */
function updateWorldPolicyHint(worldOption) {
  const policyHint = document.getElementById('play-world-policy-hint');
  const summaryHint = document.getElementById('play-account-summary-hint');
  if (!policyHint && !summaryHint) {
    return;
  }

  if (!worldOption) {
    if (policyHint) {
      policyHint.textContent = 'Select a world to view access policy.';
    }
    if (summaryHint) {
      summaryHint.textContent = 'Character creation and world entry are separate actions.';
    }
    return;
  }

  const mode = worldOption.access_mode === 'open' ? 'open' : 'invite';
  const canAccess = worldOption.can_access !== false;
  const namingMode = worldOption.naming_mode || 'generated';
  const slotLimit = Number(worldOption.slot_limit_per_account || 0);
  const usedSlots = Number(worldOption.current_character_count || 0);

  if (policyHint) {
    if (canAccess) {
      policyHint.textContent = `Access mode: ${mode}. Naming: ${namingMode}.`;
    } else {
      policyHint.textContent = 'Access mode: invite. This world is currently locked for this account.';
    }
  }
  if (summaryHint) {
    summaryHint.textContent = `World slots used: ${usedSlots}/${slotLimit}.`;
  }
}

/**
 * Enable world entry only when a concrete character is selected.
 *
 * @returns {void}
 */
function updateEnterWorldButtonState() {
  const enterWorldButton = document.getElementById('play-enter-world');
  const characterSelect = document.getElementById('play-character-select');
  if (!enterWorldButton) {
    return;
  }
  const hasCharacter = Boolean(characterSelect?.value);
  enterWorldButton.disabled = !hasCharacter;
}

/**
 * Enable character creation only when current world policy allows it.
 *
 * @returns {void}
 */
function updateCreateCharacterButtonState() {
  const createButton = document.getElementById('play-create-character');
  if (!createButton) {
    return;
  }
  const worldOption = getSelectedWorldOption();
  if (!worldOption) {
    createButton.disabled = true;
    return;
  }

  const canCreate = worldOption.can_access !== false && worldOption.can_create !== false;
  createButton.disabled = !canCreate;
}

/**
 * Return canonical world options for portal rendering.
 *
 * @param {Array<{id: string, name?: string, can_access?: boolean, can_create?: boolean, access_mode?: string, naming_mode?: string, slot_limit_per_account?: number, current_character_count?: number, is_locked?: boolean}>|undefined} worlds
 * @returns {Array<{id: string, name?: string, can_access: boolean, can_create: boolean, access_mode: string, naming_mode: string, slot_limit_per_account: number, current_character_count: number, is_locked: boolean}>}
 */
function getWorldOptions(worlds) {
  const options = Array.isArray(worlds)
    ? worlds
        .filter((entry) => entry?.id)
        .map((entry) => ({
          id: entry.id,
          name: entry.name || entry.id,
          can_access: entry.can_access !== false,
          can_create: entry.can_create !== false,
          access_mode: entry.access_mode || 'invite',
          naming_mode: entry.naming_mode || 'generated',
          slot_limit_per_account: Number(entry.slot_limit_per_account || 0),
          current_character_count: Number(entry.current_character_count || 0),
          is_locked: entry.is_locked === true || entry.can_access === false,
        }))
    : [];
  if (options.length) {
    return options;
  }
  const fallbackWorldId = getDefaultWorldId();
  return [
    {
      id: fallbackWorldId,
      name: fallbackWorldId,
      can_access: true,
      can_create: true,
      access_mode: 'open',
      naming_mode: 'generated',
      slot_limit_per_account: 10,
      current_character_count: 0,
      is_locked: false,
    },
  ];
}

/**
 * Select a default world id, preferring currently accessible worlds.
 *
 * @param {Array<{id: string, can_access?: boolean}>} worlds
 * @param {string} [selectedWorldId]
 * @returns {string}
 */
function getPreferredWorldId(worlds, selectedWorldId = '') {
  const accessible = worlds.filter((entry) => entry.can_access !== false);
  if (selectedWorldId && accessible.some((entry) => entry.id === selectedWorldId)) {
    return selectedWorldId;
  }
  if (accessible.length) {
    return accessible[0].id;
  }
  if (selectedWorldId && worlds.some((entry) => entry.id === selectedWorldId)) {
    return selectedWorldId;
  }
  return worlds[0]?.id || getDefaultWorldId();
}

/**
 * Resolve selected world metadata from current session state.
 *
 * @returns {Record<string, unknown>|null}
 */
function getSelectedWorldOption() {
  const session = readSession();
  const selectedWorldId = getSelectedWorldId();
  const worldOptions = getWorldOptions(session?.available_worlds);
  return worldOptions.find((entry) => entry.id === selectedWorldId) || null;
}

/**
 * Read current world id from the selector.
 *
 * @returns {string}
 */
function getSelectedWorldId() {
  const worldSelect = document.getElementById('play-world-select');
  return worldSelect?.value || getDefaultWorldId();
}

/**
 * Resolve currently selected character id as a number.
 *
 * @returns {number|null}
 */
function getSelectedCharacterId() {
  const characterSelect = document.getElementById('play-character-select');
  const rawValue = characterSelect?.value || '';
  const parsed = Number.parseInt(rawValue, 10);
  if (Number.isNaN(parsed)) {
    return null;
  }
  return parsed;
}

/**
 * Refresh character list for the selected world and persist the result.
 *
 * This call is the key bridge between account sessions and character-bound
 * gameplay sessions. World entry is blocked until this list contains at least
 * one character and `/characters/select` succeeds.
 *
 * @param {{sessionId: string, worldId: string, preferredCharacterId?: number|null}} params
 * @returns {Promise<void>}
 */
async function refreshCharactersForWorld({ sessionId, worldId, preferredCharacterId = null }) {
  updateCharacterHint(`Loading characters for ${worldId}...`);
  const session = readSession();
  const worldOptions = getWorldOptions(session?.available_worlds);
  const worldEntry = worldOptions.find((entry) => entry.id === worldId) || null;
  updateWorldPolicyHint(worldEntry);

  if (worldEntry && worldEntry.can_access === false) {
    populateCharacterSelect([], null);
    updateSession({
      selected_world_id: worldId,
      selected_character_id: null,
      selected_character_name: null,
    });
    updateCharacterHint(`World ${worldId} is invite-locked for this account.`);
    updateEnterWorldButtonState();
    updateCreateCharacterButtonState();
    return;
  }

  const response = await listCharacters(sessionId, worldId);
  const characters = Array.isArray(response?.characters) ? response.characters : [];

  if (worldEntry) {
    const updatedWorlds = worldOptions.map((entry) => {
      if (entry.id !== worldId) {
        return entry;
      }
      const slotLimit = Number(entry.slot_limit_per_account || 0);
      const usedSlots = characters.length;
      return {
        ...entry,
        current_character_count: usedSlots,
        can_create: usedSlots < slotLimit,
      };
    });
    updateSession({ available_worlds: updatedWorlds });
    updateWorldPolicyHint(updatedWorlds.find((entry) => entry.id === worldId) || null);
  }

  populateCharacterSelect(characters, preferredCharacterId);
  if (!characters.length) {
    updateSession({
      selected_world_id: worldId,
      selected_character_id: null,
      selected_character_name: null,
    });
    updateCharacterHint(
      `No characters are available in ${worldId}. Create one before entering this world.`
    );
    updateEnterWorldButtonState();
    updateCreateCharacterButtonState();
    return;
  }

  const selectedCharacterId = getSelectedCharacterId();
  const selectedCharacter = characters.find((entry) => Number(entry.id) === selectedCharacterId);
  updateSession({
    selected_world_id: worldId,
    selected_character_id: selectedCharacterId,
    selected_character_name: selectedCharacter?.name || null,
  });
  updateCharacterHint(`${characters.length} character(s) available in ${worldId}.`);
  updateEnterWorldButtonState();
  updateCreateCharacterButtonState();
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

  const logoutButton = document.getElementById('play-logout-button');
  if (logoutButton) {
    logoutButton.hidden = false;
  }

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
  const logoutButton = document.getElementById('play-logout-button');
  if (logoutButton) {
    logoutButton.hidden = true;
  }
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

  const logoutButton = document.getElementById('play-logout-button');
  if (logoutButton) {
    logoutButton.hidden = false;
  }

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
    const logoutButton = document.getElementById('play-logout-button');
    if (logoutButton) {
      logoutButton.hidden = false;
    }
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
