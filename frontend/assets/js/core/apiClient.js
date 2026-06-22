export const API_BASE_URL = globalThis.location?.origin || 'http://127.0.0.1:8765';
export const DEFAULT_TIMEOUT_MS = 8000;

export class ApiError extends Error {
    constructor(message, { status = 0, code = 'API_ERROR', cause = null } = {}) {
        super(message, cause ? { cause } : undefined);
        this.name = 'ApiError';
        this.status = status;
        this.code = code;
    }
}

function responseMessage(payload, status) {
    if (payload && typeof payload === 'object' && payload.detail) return String(payload.detail);
    if (typeof payload === 'string' && payload.trim()) return payload.trim();
    return `La API respondió con HTTP ${status}.`;
}

export async function apiRequest(path, options = {}) {
    const {
        timeoutMs = DEFAULT_TIMEOUT_MS,
        headers = {},
        body,
        signal,
        ...fetchOptions
    } = options;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    const abortFromCaller = () => controller.abort();
    signal?.addEventListener('abort', abortFromCaller, { once: true });

    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    const requestBody = body && !isFormData && typeof body !== 'string'
        ? JSON.stringify(body)
        : body;

    try {
        const response = await fetch(`${API_BASE_URL}${path}`, {
            credentials: 'include',
            ...fetchOptions,
            body: requestBody,
            headers: {
                Accept: 'application/json',
                ...(requestBody && !isFormData ? { 'Content-Type': 'application/json' } : {}),
                ...headers,
            },
            signal: controller.signal,
        });
        const contentType = response.headers.get('content-type') || '';
        const payload = response.status === 204
            ? null
            : contentType.includes('application/json')
                ? await response.json()
                : await response.text();
        if (!response.ok) {
            throw new ApiError(responseMessage(payload, response.status), {
                status: response.status,
                code: 'HTTP_ERROR',
            });
        }
        return payload;
    } catch (error) {
        if (error instanceof ApiError) throw error;
        if (controller.signal.aborted) {
            throw new ApiError('El backend local tardó demasiado en responder.', {
                code: 'TIMEOUT',
                cause: error,
            });
        }
        throw new ApiError('El backend local no está disponible. Life OS seguirá con datos locales.', {
            code: 'BACKEND_UNAVAILABLE',
            cause: error,
        });
    } finally {
        clearTimeout(timeout);
        signal?.removeEventListener('abort', abortFromCaller);
    }
}

export function createLocalSession() {
    return apiRequest('/api/session', { method: 'POST', timeoutMs: 4000 });
}

export function getApiHealth() {
    return apiRequest('/api/health', { timeoutMs: 4000 });
}
