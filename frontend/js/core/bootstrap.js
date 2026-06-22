import { LifeOSApi } from './api.js';
import {
    checkBackendStatus,
    getBackendStatus,
    initializeBackendStatus,
} from '../../assets/js/core/backendStatus.js';
import { dataProvider } from '../../assets/js/core/dataProvider.js';
import {
    FEATURE_FLAGS,
    FINANCE_WRITE_FLAGS,
    HEALTH_CAR_WRITE_FLAGS,
    setFinanceWriteFlag,
    setHealthCarWriteFlag,
} from '../../assets/js/core/featureFlags.js';
import { dashboardBridge } from '../../assets/js/domains/dashboardBridge.js';
import { financeParity } from '../../assets/js/domains/financeParity.js';
import { healthCarParity } from '../../assets/js/domains/healthCarParity.js';

const api = new LifeOSApi();
const PHOTO_DB_NAME = 'lifeos_photo_db_v1';
const PHOTO_STORE_NAME = 'photos';
const PHOTO_FALLBACK_KEY = 'lifeos_progress_photos_v1';

function setStatus(message, tone = 'text-slate-500') {
    const element = document.getElementById('v1-backend-status');
    if (!element) return;
    element.className = `text-sm ${tone}`;
    element.textContent = message;
}

function setResult(payload) {
    const element = document.getElementById('v1-migration-result');
    if (!element) return;
    element.textContent = JSON.stringify(payload, null, 2);
    element.classList.remove('hidden');
}

function readPhotosFromIndexedDb() {
    return new Promise((resolve) => {
        if (!('indexedDB' in window)) {
            resolve([]);
            return;
        }
        const request = indexedDB.open(PHOTO_DB_NAME, 1);
        request.onerror = () => resolve([]);
        request.onupgradeneeded = () => resolve([]);
        request.onsuccess = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains(PHOTO_STORE_NAME)) {
                db.close();
                resolve([]);
                return;
            }
            const transaction = db.transaction(PHOTO_STORE_NAME, 'readonly');
            const getAll = transaction.objectStore(PHOTO_STORE_NAME).getAll();
            getAll.onerror = () => resolve([]);
            getAll.onsuccess = () => {
                db.close();
                resolve(getAll.result || []);
            };
        };
    });
}

async function legacyPayload() {
    const rawState = localStorage.getItem('lifeos_data_v2');
    if (!rawState) throw new Error('No hay datos lifeos_data_v2 en este navegador.');
    const state = JSON.parse(rawState);
    const credentialCount = Array.isArray(state?.credentials?.entries)
        ? state.credentials.entries.length
        : 0;
    delete state.credentials;
    let photos = await readPhotosFromIndexedDb();
    if (!photos.length) {
        try {
            photos = JSON.parse(localStorage.getItem(PHOTO_FALLBACK_KEY) || '[]');
        } catch {
            photos = [];
        }
    }
    return {
        app: 'LifeOS',
        version: 3,
        exportedAt: new Date().toISOString(),
        state,
        photos,
        migrationMetadata: {
            credentialsExcludedByClient: credentialCount,
        },
    };
}

async function runMigration(mode) {
    setStatus(
        mode === 'preview'
            ? 'Analizando los datos locales sin escribir en SQLite...'
            : 'Creando backup y migrando a SQLite...',
        'text-blue-400',
    );
    const payload = await legacyPayload();
    const result = await api.importLegacy(payload, mode);
    setResult(result);
    setStatus(
        mode === 'preview'
            ? 'Vista previa lista. No se modificaron tus datos.'
            : 'Migración terminada. localStorage permanece intacto como respaldo.',
        'text-emerald-500',
    );
    return result;
}

window.previewLifeOSMigration = async () => {
    try {
        await runMigration('preview');
    } catch (error) {
        setStatus(`No se pudo analizar: ${error.message}`, 'text-red-500');
    }
};

window.commitLifeOSMigration = async () => {
    const confirmed = window.confirm(
        'Se creará un backup local y se copiarán tus datos a SQLite. localStorage no se borrará. ¿Continuar?',
    );
    if (!confirmed) return;
    try {
        await runMigration('commit');
    } catch (error) {
        setStatus(`No se pudo migrar: ${error.message}`, 'text-red-500');
    }
};

window.createLifeOSV1Backup = async () => {
    try {
        setStatus('Creando backup V1...', 'text-blue-400');
        const result = await api.createBackup('frontend-manual');
        setResult(result);
        setStatus('Backup V1 creado en la carpeta privada de Life OS.', 'text-emerald-500');
    } catch (error) {
        setStatus(`No se pudo crear el backup: ${error.message}`, 'text-red-500');
    }
};

async function bootstrap() {
    if (!['http:', 'https:'].includes(window.location.protocol)) {
        setStatus('Abre Life OS desde http://127.0.0.1:8765 para usar el backend.', 'text-yellow-500');
        return;
    }
    initializeBackendStatus();
}

window.lifeOSApi = api;
window.lifeOSBackend = {
    check: checkBackendStatus,
    getStatus: getBackendStatus,
};
window.lifeOSDataProvider = dataProvider;
window.lifeOSDashboardBridge = dashboardBridge;
window.lifeOSFinanceParity = financeParity;
window.lifeOSHealthCarParity = healthCarParity;
window.LIFE_OS_FEATURE_FLAGS = FEATURE_FLAGS;
window.LIFE_OS_FINANCE_WRITE_FLAGS = FINANCE_WRITE_FLAGS;
window.LIFE_OS_HEALTH_CAR_WRITE_FLAGS = HEALTH_CAR_WRITE_FLAGS;
window.setLifeOSFinanceWriteFlag = setFinanceWriteFlag;
window.setLifeOSHealthCarWriteFlag = setHealthCarWriteFlag;
window.setLifeOSHealthWriteFlag = (flag, enabled) => setHealthCarWriteFlag(flag, enabled);
window.setLifeOSRoutineWriteFlag = (flag, enabled) => setHealthCarWriteFlag(flag, enabled);
window.setLifeOSCarWriteFlag = (flag, enabled) => setHealthCarWriteFlag(flag, enabled);
window.addEventListener('DOMContentLoaded', bootstrap);
