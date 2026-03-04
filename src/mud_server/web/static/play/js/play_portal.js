/*
 * play_portal.js
 *
 * World-selection and account-portal helpers for the play shell.
 */

import { listCharacters } from './play_api.js';
import { readSession, updateSession } from './play_session.js';

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
 * Read current world id from the selector.
 *
 * @returns {string}
 */
function getSelectedWorldId() {
  const worldSelect = document.getElementById('play-world-select');
  return worldSelect?.value || getDefaultWorldId();
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

export {
  getDefaultWorldId,
  getPreferredWorldId,
  getSelectedCharacterId,
  getSelectedWorldId,
  getSelectedWorldOption,
  getWorldId,
  getWorldOptions,
  populateCharacterSelect,
  populateWorldSelect,
  refreshCharactersForWorld,
  updateCharacterHint,
  updateCreateCharacterButtonState,
  updateEnterWorldButtonState,
  updateWorldPolicyHint,
};
