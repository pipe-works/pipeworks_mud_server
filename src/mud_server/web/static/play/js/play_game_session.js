/*
 * play_game_session.js
 *
 * In-world command submission and chat polling helpers for the play shell.
 */

import { apiCall, getErrorMessage } from './play_api.js';

/** @type {ReturnType<typeof setInterval>|null} */
let _chatPollInterval = null;
/** @type {string[]} */
let _prevChatLines = [];

/**
 * Stop the active chat polling loop if one is running.
 *
 * @returns {void}
 */
function stopChatPolling() {
  if (_chatPollInterval !== null) {
    clearInterval(_chatPollInterval);
    _chatPollInterval = null;
  }
}

/**
 * Decode HTML entities in a string without introducing XSS risk.
 *
 * @param {string} str
 * @returns {string}
 */
function decodeHtmlEntities(str) {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = str;
  return textarea.value;
}

/**
 * Append a line of text to the game output window and scroll to the bottom.
 *
 * @param {string} text
 * @param {string} [cssClass]
 * @returns {void}
 */
function appendToOutput(text, cssClass = 'output-text') {
  const output = document.getElementById('gameOutput');
  if (!output) {
    return;
  }
  const entry = document.createElement('div');
  entry.className = cssClass;
  entry.textContent = decodeHtmlEntities(text);
  output.appendChild(entry);
  output.scrollTop = output.scrollHeight;
}

/**
 * Send a command to POST /command and append the response to the output.
 *
 * @param {string} sessionId
 * @param {string} command
 * @returns {Promise<void>}
 */
async function submitCommand(sessionId, command) {
  appendToOutput(`> ${command}`, 'output-command');
  try {
    const response = await apiCall('/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, command }),
    });
    if (response.message) {
      appendToOutput(response.message, response.success ? 'output-text' : 'output-error');
    }
  } catch (err) {
    appendToOutput(`Error: ${getErrorMessage(err)}`, 'output-error');
  }
}

/**
 * Poll GET /chat/{sessionId} and append any new messages to the output.
 *
 * @param {string} sessionId
 * @returns {Promise<void>}
 */
async function pollChat(sessionId) {
  try {
    const data = await apiCall(`/chat/${sessionId}`, { method: 'GET' });
    const chatStr = typeof data?.chat === 'string' ? data.chat : '';
    if (!chatStr) {
      return;
    }
    const lines = chatStr.split('\n').filter((line) => line.trim() && !line.startsWith('['));
    if (lines.length === 0) {
      _prevChatLines = [];
      return;
    }

    let newStart = 0;
    for (let i = _prevChatLines.length - 1; i >= 0; i -= 1) {
      const idx = lines.lastIndexOf(_prevChatLines[i]);
      if (idx !== -1) {
        newStart = idx + 1;
        break;
      }
    }
    for (const msg of lines.slice(newStart)) {
      appendToOutput(msg, 'output-chat');
    }
    _prevChatLines = lines;
  } catch (_err) {
    // Don't disrupt gameplay on transient chat poll failures.
  }
}

/**
 * Bind the Enter key on the command input to submit commands.
 *
 * @param {string} sessionId
 * @returns {void}
 */
function bindCommandInput(sessionId) {
  const input = document.getElementById('commandInput');
  if (!input) {
    return;
  }
  input.addEventListener('keydown', async (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      const command = input.value.trim();
      if (!command) {
        return;
      }
      input.value = '';
      await submitCommand(sessionId, command);
    }
  });
  input.focus();
}

/**
 * Start an in-world game session: clear the output, fire an initial look,
 * seed the chat baseline, and begin polling for new messages.
 *
 * @param {string} _worldId
 * @param {string} sessionId
 * @returns {Promise<void>}
 */
async function startGameSession(_worldId, sessionId) {
  const output = document.getElementById('gameOutput');
  if (output) {
    output.innerHTML = '';
  }
  _prevChatLines = [];

  bindCommandInput(sessionId);
  await submitCommand(sessionId, 'look');

  try {
    const data = await apiCall(`/chat/${sessionId}`, { method: 'GET' });
    const chatStr = typeof data?.chat === 'string' ? data.chat : '';
    const lines = chatStr.split('\n').filter((line) => line.trim() && !line.startsWith('['));
    _prevChatLines = lines;
  } catch (_err) {
    // Polling will recover on the first tick.
  }

  stopChatPolling();
  _chatPollInterval = setInterval(() => pollChat(sessionId), 5000);
}

export { startGameSession, stopChatPolling };
