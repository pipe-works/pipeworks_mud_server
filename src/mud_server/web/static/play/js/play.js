/*
 * play.js
 *
 * Base bootstrap for the play shell. This script manages the three UI states:
 * 1) Logged out (permit issuance)
 * 2) World selection
 * 3) In-world UI
 *
 * World-specific scripts can extend this behavior when /play/<world_id> is used.
 */

const STORAGE_KEY = 'pipeworks_play_session';

function getWorldId() {
  const root = document.body;
  return root?.dataset?.worldId || '';
}

function getDefaultWorldId() {
  return getWorldId() || 'pipeworks_web';
}

function getStateElements() {
  return {
    loggedOut: document.querySelector('[data-play-state="logged-out"]'),
    selectWorld: document.querySelector('[data-play-state="select-world"]'),
    inWorld: document.querySelector('[data-play-state="in-world"]'),
  };
}

function setState(state) {
  const { loggedOut, selectWorld, inWorld } = getStateElements();
  if (loggedOut) loggedOut.hidden = state !== 'logged-out';
  if (selectWorld) selectWorld.hidden = state !== 'select-world';
  if (inWorld) inWorld.hidden = state !== 'in-world';
}

function readSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return null;
  }
}

function writeSession(payload) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function clearSession() {
  sessionStorage.removeItem(STORAGE_KEY);
}

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
    throw new Error(message);
  }
  return data;
}

function randomPassword() {
  const alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let result = '';
  for (let i = 0; i < 16; i += 1) {
    result += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return result;
}

async function registerGuest({ password, characterName }) {
  return apiCall('/register-guest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      password,
      password_confirm: password,
      character_name: characterName,
    }),
  });
}

async function login({ username, password }) {
  return apiCall('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
}

async function logout(sessionId) {
  return apiCall('/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

async function getStatus(sessionId) {
  return apiCall(`/status/${sessionId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
}

function updateStatus(message) {
  const status = document.getElementById('play-status');
  if (status) {
    status.textContent = message;
  }
}

function updateCharacterName(name) {
  const label = document.getElementById('play-character-name-display');
  if (label) {
    label.textContent = name;
  }
}

function populateWorldSelect(worlds) {
  const select = document.getElementById('play-world-select');
  if (!select) {
    return;
  }

  select.innerHTML = '';
  worlds.forEach((world) => {
    const option = document.createElement('option');
    option.value = world.id;
    option.textContent = world.name || world.id;
    select.appendChild(option);
  });
}

function updateLocation(message) {
  const element = document.getElementById('play-location');
  if (element) {
    element.textContent = message;
  }
}

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

  writeSession({
    session_id: loginResponse.session_id,
    username: accountUsername,
    account_username: accountUsername,
    role: loginResponse.role || null,
    available_worlds: loginResponse.available_worlds || [],
  });

  const logoutButton = document.getElementById('play-logout-button');
  if (logoutButton) {
    logoutButton.hidden = false;
  }

  updateStatus(`Logged in as ${accountUsername}.`);
  updateCharacterName(accountUsername);
  updateLocation('Select a world to continue.');

  const worlds = loginResponse.available_worlds || [];
  populateWorldSelect(worlds.length ? worlds : [{ id: getDefaultWorldId() }]);
  setState('select-world');
}

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
  updateCharacterName('Character Name');
  const logoutButton = document.getElementById('play-logout-button');
  if (logoutButton) {
    logoutButton.hidden = true;
  }
}

function bindEvents() {
  const loginButton = document.getElementById('play-login-button');
  const logoutButton = document.getElementById('play-logout-button');
  const enterWorldButton = document.getElementById('play-enter-world');
  const worldSelect = document.getElementById('play-world-select');

  if (loginButton) {
    loginButton.addEventListener('click', async () => {
      loginButton.disabled = true;
      try {
        await handleLogin();
      } catch (err) {
        updateStatus(`Goblin says: ${err.message}`);
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
        updateStatus(`Goblin says: ${err.message}`);
      } finally {
        logoutButton.disabled = false;
      }
    });
  }

  if (enterWorldButton) {
    enterWorldButton.addEventListener('click', () => {
      const selectedWorld = worldSelect?.value || getDefaultWorldId();
      window.location.assign(`/play/${selectedWorld}`);
    });
  }
}

async function hydrateSession() {
  const session = readSession();
  if (!session?.session_id) {
    setState('logged-out');
    return;
  }

  updateStatus('Checking existing session...');
  try {
    const status = await getStatus(session.session_id);
    if (!status?.session_id) {
      throw new Error('Session invalid');
    }
    updateCharacterName(session.username || 'Unknown');
    updateLocation('Session active.');
    const worlds = session.available_worlds || [];
    populateWorldSelect(worlds.length ? worlds : [{ id: getDefaultWorldId() }]);
    setState('select-world');
  } catch (err) {
    clearSession();
    setState('logged-out');
    updateStatus('Session expired. Awaiting credentials.');
  }
}

function initPlayShell() {
  const worldId = getWorldId();
  bindEvents();

  if (worldId) {
    setState('in-world');
    updateLocation(`Entering ${worldId}...`);
    const logoutButton = document.getElementById('play-logout-button');
    if (logoutButton) {
      logoutButton.hidden = false;
    }
    return;
  }

  hydrateSession();
}

initPlayShell();
