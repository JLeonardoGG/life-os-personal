import assert from 'node:assert/strict';
import test from 'node:test';

import {
    API_BASE_URL,
    ApiError,
    apiRequest,
} from '../../frontend/assets/js/core/apiClient.js';

test('apiRequest parses JSON and uses the local backend', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
        assert.equal(url, `${API_BASE_URL}/api/health`);
        assert.equal(options.credentials, 'include');
        return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        });
    };
    try {
        assert.deepEqual(await apiRequest('/api/health'), { status: 'ok' });
    } finally {
        globalThis.fetch = originalFetch;
    }
});

test('apiRequest returns a clear backend unavailable error', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
        throw new TypeError('fetch failed');
    };
    try {
        await assert.rejects(
            apiRequest('/api/health'),
            (error) => error instanceof ApiError && error.code === 'BACKEND_UNAVAILABLE',
        );
    } finally {
        globalThis.fetch = originalFetch;
    }
});
