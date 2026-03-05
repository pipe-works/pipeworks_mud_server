import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildWorldOptions,
  filterUsers,
  resolveCreateCharacterWorldId,
  resolveSelectedUser,
  sortUsers,
} from '../../src/mud_server/web/static/js/pages/users_state.js';

test('filterUsers drops tombstoned rows and applies active/online flags', () => {
  const users = [
    {
      id: 1,
      username: 'alice',
      role: 'player',
      account_origin: 'local',
      is_active: true,
      is_online_account: true,
      is_online_in_world: false,
      tombstoned_at: null,
    },
    {
      id: 2,
      username: 'bob',
      role: 'admin',
      account_origin: 'local',
      is_active: false,
      is_online_account: false,
      is_online_in_world: false,
      tombstoned_at: null,
    },
    {
      id: 3,
      username: 'legacy',
      role: 'player',
      account_origin: 'import',
      is_active: true,
      is_online_account: true,
      is_online_in_world: true,
      tombstoned_at: '2026-01-01T00:00:00Z',
    },
  ];

  const activeOnline = filterUsers(users, '', true, true);
  assert.equal(activeOnline.length, 1);
  assert.equal(activeOnline[0].username, 'alice');
});

test('filterUsers search matches username, role, and origin', () => {
  const users = [
    {
      id: 1,
      username: 'charlie',
      role: 'worldbuilder',
      account_origin: 'provisioned',
      is_active: true,
      is_online_account: false,
      is_online_in_world: false,
      tombstoned_at: null,
    },
  ];

  assert.equal(filterUsers(users, 'char', false, false).length, 1);
  assert.equal(filterUsers(users, 'worldbuilder', false, false).length, 1);
  assert.equal(filterUsers(users, 'provisioned', false, false).length, 1);
});

test('sortUsers respects username sort direction', () => {
  const users = [
    { username: 'zeta', role: 'player', is_active: true, is_online_account: false, is_online_in_world: false },
    { username: 'alpha', role: 'player', is_active: true, is_online_account: false, is_online_in_world: false },
  ];

  const asc = sortUsers(users, { key: 'username', direction: 'asc' });
  assert.deepEqual(
    asc.map((entry) => entry.username),
    ['alpha', 'zeta']
  );

  const desc = sortUsers(users, { key: 'username', direction: 'desc' });
  assert.deepEqual(
    desc.map((entry) => entry.username),
    ['zeta', 'alpha']
  );
});

test('resolveSelectedUser keeps valid selection and falls back when missing', () => {
  const sortedUsers = [{ id: 10 }, { id: 11 }];

  const keep = resolveSelectedUser(sortedUsers, 11);
  assert.equal(keep.selectedUserId, 11);
  assert.equal(keep.selectedUser.id, 11);

  const fallback = resolveSelectedUser(sortedUsers, 99);
  assert.equal(fallback.selectedUserId, 10);
  assert.equal(fallback.selectedUser.id, 10);
});

test('buildWorldOptions sorts by id and selection resolver keeps valid world id', () => {
  const worldsById = new Map([
    ['z_world', 'Zed'],
    ['a_world', 'Aye'],
  ]);
  const options = buildWorldOptions(worldsById);
  assert.deepEqual(
    options.map((entry) => entry.id),
    ['a_world', 'z_world']
  );

  assert.equal(resolveCreateCharacterWorldId('z_world', options), 'z_world');
  assert.equal(resolveCreateCharacterWorldId('missing', options), 'a_world');
});
