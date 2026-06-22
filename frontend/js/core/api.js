export class LifeOSApi {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    async request(path, options = {}) {
        const response = await fetch(`${this.baseUrl}${path}`, {
            credentials: 'same-origin',
            headers: {
                ...(options.body && !(options.body instanceof FormData)
                    ? { 'Content-Type': 'application/json' }
                    : {}),
                ...(options.headers || {}),
            },
            ...options,
        });
        const contentType = response.headers.get('content-type') || '';
        const payload = contentType.includes('application/json')
            ? await response.json()
            : await response.text();
        if (!response.ok) {
            const detail = payload?.detail || payload || `HTTP ${response.status}`;
            throw new Error(String(detail));
        }
        return payload;
    }

    createSession() {
        return this.request('/api/session', { method: 'POST' });
    }

    health() {
        return this.request('/api/health');
    }

    importLegacy(payload, mode = 'preview') {
        return this.request(`/api/import/localstorage?mode=${encodeURIComponent(mode)}`, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    createBackup(reason = 'frontend') {
        return this.request(`/api/backup/create?reason=${encodeURIComponent(reason)}`, {
            method: 'POST',
        });
    }
}
