import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getDefaultWorldId,
  getPreferredWorldId,
  getWorldOptions,
} from '../../src/mud_server/web/static/play/js/play_portal.js';

test.beforeEach(() => {
  globalThis.document = {
    body: {
      dataset: {
        worldId: 'test_world',
      },
    },
  };
});

test('getWorldOptions canonicalizes flags and numeric values', () => {
  const options = getWorldOptions([
    {
      id: 'alpha',
      can_access: false,
      can_create: true,
      access_mode: 'invite',
      naming_mode: 'generated',
      slot_limit_per_account: '3',
      current_character_count: '1',
      is_locked: false,
    },
  ]);

  assert.equal(options.length, 1);
  assert.equal(options[0].id, 'alpha');
  assert.equal(options[0].can_access, false);
  assert.equal(options[0].is_locked, true);
  assert.equal(options[0].slot_limit_per_account, 3);
  assert.equal(options[0].current_character_count, 1);
});

test('getWorldOptions falls back to route world id when list is empty', () => {
  const options = getWorldOptions(undefined);
  assert.equal(options.length, 1);
  assert.equal(options[0].id, 'test_world');
  assert.equal(getDefaultWorldId(), 'test_world');
});

test('getPreferredWorldId prioritizes selected accessible world', () => {
  const worlds = [
    { id: 'locked', can_access: false },
    { id: 'open_a', can_access: true },
    { id: 'open_b', can_access: true },
  ];

  assert.equal(getPreferredWorldId(worlds, 'open_b'), 'open_b');
  assert.equal(getPreferredWorldId(worlds, 'locked'), 'open_a');
  assert.equal(getPreferredWorldId(worlds, ''), 'open_a');
});
