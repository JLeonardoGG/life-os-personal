import { createLocalSession, getApiHealth } from './apiClient.js';

export const BACKEND_STATES = Object.freeze({
    ONLINE: 'online',
    OFFLINE: 'offline',
    UNKNOWN: 'unknown',
});

let currentStatus = {
    state: BACKEND_STATES.UNKNOWN,
    checkedAt: null,
    health: null,
    errorCode: null,
};
const subscribers = new Set();

export function getBackendStatus() {
    return { ...currentStatus };
}

export function subscribeBackendStatus(callback) {
    subscribers.add(callback);
    callback(getBackendStatus());
    return () => subscribers.delete(callback);
}

function publish(nextStatus) {
    currentStatus = {
        ...currentStatus,
        ...nextStatus,
        checkedAt: new Date().toISOString(),
    };
    subscribers.forEach((callback) => callback(getBackendStatus()));
    if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('lifeos:backend-status', {
            detail: getBackendStatus(),
        }));
    }
}

export async function checkBackendStatus() {
    try {
        const health = await getApiHealth();
        await createLocalSession();
        publish({
            state: BACKEND_STATES.ONLINE,
            health,
            errorCode: null,
        });
    } catch (error) {
        publish({
            state: BACKEND_STATES.OFFLINE,
            health: null,
            errorCode: error.code || 'BACKEND_UNAVAILABLE',
        });
    }
    return getBackendStatus();
}

function statusPresentation(status) {
    if (status.state === BACKEND_STATES.ONLINE) {
        return {
            text: 'Backend conectado',
            detail: 'SQLite disponible',
            className: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
            iconClass: 'bg-emerald-400',
        };
    }
    if (status.state === BACKEND_STATES.OFFLINE) {
        return {
            text: 'Backend no disponible',
            detail: 'Usando localStorage fallback',
            className: 'text-yellow-200 border-yellow-500/30 bg-yellow-500/10',
            iconClass: 'bg-yellow-400',
        };
    }
    return {
        text: 'Comprobando backend',
        detail: 'Fuente pendiente',
        className: 'text-slate-300 border-slate-600 bg-slate-800/70',
        iconClass: 'bg-slate-400',
    };
}

export function renderBackendStatus(status = getBackendStatus()) {
    if (typeof document === 'undefined') return;
    const presentation = statusPresentation(status);
    const indicator = document.getElementById('lifeos-backend-indicator');
    if (indicator) {
        indicator.className = `mx-4 mb-3 rounded-lg border px-3 py-2 text-xs ${presentation.className}`;
        indicator.innerHTML = `
            <div class="flex items-center gap-2">
                <span class="h-2 w-2 rounded-full ${presentation.iconClass}"></span>
                <span class="font-semibold">${presentation.text}</span>
            </div>
            <p class="mt-1 text-[10px] opacity-75">${presentation.detail}</p>
        `;
    }
    const settingsStatus = document.getElementById('v1-backend-status');
    if (settingsStatus) {
        settingsStatus.className = status.state === BACKEND_STATES.ONLINE
            ? 'text-sm text-emerald-500'
            : status.state === BACKEND_STATES.OFFLINE
                ? 'text-sm text-yellow-500'
                : 'text-sm text-slate-500';
        settingsStatus.textContent = status.state === BACKEND_STATES.ONLINE
            ? `Backend V1 activo · SQLite OK · IA ${status.health?.ai_enabled ? 'habilitada' : 'desactivada'}.`
            : status.state === BACKEND_STATES.OFFLINE
                ? 'Backend no disponible · Life OS continúa con localStorage fallback.'
                : 'Comprobando backend local...';
    }
}

export function initializeBackendStatus({ pollIntervalMs = 30000 } = {}) {
    subscribeBackendStatus(renderBackendStatus);
    checkBackendStatus();
    return setInterval(checkBackendStatus, pollIntervalMs);
}
