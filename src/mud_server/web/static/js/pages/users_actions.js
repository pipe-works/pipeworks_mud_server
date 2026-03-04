/*
 * users_actions.js
 *
 * Prompt/confirm-driven action helpers for the admin Users page. The current
 * UX intentionally stays browser-native in the incremental refactor phase, but
 * the request/feedback orchestration no longer needs to live in users.js.
 */

import { showToast } from '../ui/toasts.js';

/**
 * Run an account-management action from the users table.
 *
 * @param {object} params
 * @param {object} params.api
 * @param {string} params.sessionId
 * @param {string} params.action
 * @param {string} params.username
 * @param {() => Promise<void>} params.refresh
 * @returns {Promise<void>}
 */
async function handleUserAction({ api, sessionId, action, username, refresh }) {
  let payload = {
    session_id: sessionId,
    action,
    target_username: username,
  };

  if (action === 'change_role') {
    const newRole = prompt('Enter new role (player, worldbuilder, admin, superuser):');
    if (!newRole) {
      return;
    }
    payload = { ...payload, new_role: newRole.trim().toLowerCase() };
  }

  if (action === 'change_password') {
    const newPassword = prompt('Enter new password (min 8 chars):');
    if (!newPassword) {
      return;
    }
    payload = { ...payload, new_password: newPassword };
  }

  if (action === 'delete') {
    const confirmed = confirm(`Delete user ${username}? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
  }

  try {
    await api.manageUser(payload);
    showToast(`Action '${action}' completed.`, 'success');
    await refresh();
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Action failed.', 'error');
  }
}

/**
 * Run a character-management action from the selected user's Characters tab.
 *
 * @param {object} params
 * @param {object} params.api
 * @param {string} params.sessionId
 * @param {string} params.action
 * @param {string} params.characterId
 * @param {string} params.characterName
 * @param {() => Promise<void>} params.refresh
 * @param {(value: string|null) => void} params.setPendingActionKey
 * @returns {Promise<void>}
 */
async function handleCharacterAction({
  api,
  sessionId,
  action,
  characterId,
  characterName,
  refresh,
  setPendingActionKey,
}) {
  const key = `${action}:${characterId}`;
  const actionLabel = action === 'tombstone' ? 'tombstone' : 'permanently delete';
  const warning =
    action === 'tombstone'
      ? `Tombstone character "${characterName}"?`
      : `Permanently delete character "${characterName}"? This cannot be undone.`;
  if (!confirm(warning)) {
    return;
  }

  setPendingActionKey(key);
  try {
    await api.manageCharacter({
      session_id: sessionId,
      character_id: Number(characterId),
      action,
    });
    showToast(`Character "${characterName}" ${actionLabel}d.`, 'success');
    await refresh();
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Character action failed.', 'error');
  } finally {
    setPendingActionKey(null);
  }
}

export { handleCharacterAction, handleUserAction };
