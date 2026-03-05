import assert from 'node:assert/strict';
import test from 'node:test';

import {
  apiCall,
  buildCharacterListParams,
  getErrorMessage,
} from '../../src/mud_server/web/static/play/js/play_api.js';

test('buildCharacterListParams includes legacy-default exclusion flag', () => {
  const params = buildCharacterListParams('session-1', 'pipeworks_web');
  assert.equal(params.get('session_id'), 'session-1');
  assert.equal(params.get('world_id'), 'pipeworks_web');
  assert.equal(params.get('exclude_legacy_defaults'), 'true');
});

test('getErrorMessage normalizes unknown values', () => {
  assert.equal(getErrorMessage(new Error('nope')), 'nope');
  assert.equal(getErrorMessage('oops'), 'Unexpected error.');
});

test('apiCall throws parsed API error messages for non-2xx JSON responses', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: 'bad request' }), {
        status: 400,
        headers: { 'content-type': 'application/json' },
      });

    await assert.rejects(apiCall('/any', { method: 'GET' }), /bad request/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('apiCall throws on non-JSON responses', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      new Response('plain text', {
        status: 500,
        headers: { 'content-type': 'text/plain' },
      });

    await assert.rejects(apiCall('/any', { method: 'GET' }), /Unexpected response/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
