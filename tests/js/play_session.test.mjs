import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clearSession,
  consumeFlashMessage,
  readSession,
  updateSession,
  writeFlashMessage,
  writeSession,
} from '../../src/mud_server/web/static/play/js/play_session.js';

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

test.beforeEach(() => {
  globalThis.sessionStorage = createMemoryStorage();
});

test('writeSession and readSession round trip payloads', () => {
  writeSession({ session_id: 'abc', selected_world_id: 'pipeworks_web' });
  const session = readSession();
  assert.equal(session.session_id, 'abc');
  assert.equal(session.selected_world_id, 'pipeworks_web');
});

test('updateSession merges patch data into existing payload', () => {
  writeSession({ session_id: 'abc', role: 'player' });
  updateSession({ selected_world_id: 'pipeworks_web' });
  const session = readSession();
  assert.equal(session.session_id, 'abc');
  assert.equal(session.role, 'player');
  assert.equal(session.selected_world_id, 'pipeworks_web');
});

test('clearSession removes stored payload', () => {
  writeSession({ session_id: 'abc' });
  clearSession();
  assert.equal(readSession(), null);
});

test('flash message is one-time and consumed once', () => {
  writeFlashMessage('hello');
  assert.equal(consumeFlashMessage(), 'hello');
  assert.equal(consumeFlashMessage(), '');
});

test('readSession returns null for malformed json payload', () => {
  globalThis.sessionStorage.setItem('pipeworks_play_session', '{invalid');
  assert.equal(readSession(), null);
});
