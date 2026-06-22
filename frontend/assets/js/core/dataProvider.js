import {
    apiRequest,
    createLocalSession,
} from './apiClient.js';
import {
    BACKEND_STATES,
    checkBackendStatus,
    getBackendStatus,
} from './backendStatus.js';
import {
    FEATURE_FLAGS,
    FINANCE_WRITE_FLAGS,
    HEALTH_CAR_WRITE_FLAGS,
} from './featureFlags.js';

const LEGACY_STORAGE_KEY = 'lifeos_data_v2';
const DOMAIN_FLAGS = {
    summary: 'useApiForSummary',
    transactions: 'useApiForTransactions',
    budgets: 'useApiForBudgets',
    subscriptions: 'useApiForSubscriptions',
    debts: 'useApiForDebts',
    investments: 'useApiForInvestments',
    tasks: 'useApiForTasks',
    events: 'useApiForEvents',
    health: 'useApiForHealth',
    routines: 'useApiForRoutines',
    car: 'useApiForCar',
    tax: 'useApiForTax',
};
const sourceByDomain = new Map();

export class DataProviderError extends Error {
    constructor(message, code = 'DATA_PROVIDER_ERROR', cause = null) {
        super(message, cause ? { cause } : undefined);
        this.name = 'DataProviderError';
        this.code = code;
    }
}

function safeLog(level, message, metadata = {}) {
    const logger = console[level] || console.info;
    logger(`[LifeOS DataProvider] ${message}`, {
        domain: metadata.domain,
        source: metadata.source,
        code: metadata.code,
        count: metadata.count,
    });
}

export function readLegacyState() {
    try {
        const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch {
        safeLog('warn', 'No se pudo leer el estado heredado.', {
            source: 'localStorage',
            code: 'INVALID_LOCAL_STATE',
        });
        return null;
    }
}

export function writeLegacyState(state) {
    localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify(state));
}

export function getDomainSource(domain) {
    return sourceByDomain.get(domain) || 'unknown';
}

function setDomainSource(domain, source, detail = {}) {
    sourceByDomain.set(domain, source);
    if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('lifeos:data-source', {
            detail: { domain, source, ...detail },
        }));
    }
}

function isApiEnabled(domain) {
    const flag = DOMAIN_FLAGS[domain];
    return Boolean(flag && FEATURE_FLAGS[flag]);
}

async function ensureBackendReady() {
    let status = getBackendStatus();
    if (status.state === BACKEND_STATES.UNKNOWN) status = await checkBackendStatus();
    if (status.state !== BACKEND_STATES.ONLINE) return false;
    await createLocalSession();
    return true;
}

function hasRecords(value) {
    if (Array.isArray(value)) return value.length > 0;
    if (value && Array.isArray(value.items)) return value.items.length > 0;
    if (value && typeof value === 'object') {
        if (Array.isArray(value.logs) || Array.isArray(value.reminders)) {
            return Number(value.logs?.length || 0)
                + Number(value.reminders?.length || 0)
                + Number(Boolean(Object.keys(value.summary?.profile || {}).length)) > 0;
        }
        if (Array.isArray(value.kmLogs) || Array.isArray(value.services)) {
            return Number(value.kmLogs?.length || 0)
                + Number(value.services?.length || 0)
                + Number(value.maintenanceLogs?.length || 0)
                + Number(Boolean(Object.keys(value.profile || {}).length)) > 0;
        }
        if (Array.isArray(value.entities) || Array.isArray(value.transactions)) {
            return Number(value.entities?.length || 0) + Number(value.transactions?.length || 0) > 0;
        }
        if (value.finance || value.tasks || value.events) {
            return Number(value.finance?.transaction_count || 0)
                + Number(value.tasks?.open_due_count || 0)
                + Number(value.events?.count || 0) > 0;
        }
        return Number(value.total || value.count || value.document_count || 0) > 0;
    }
    return Boolean(value);
}

async function fallbackResult(domain, fallbackOperation, reason) {
    if (!FEATURE_FLAGS.allowLocalStorageFallback || typeof fallbackOperation !== 'function') {
        throw reason;
    }
    const data = await fallbackOperation();
    setDomainSource(domain, 'localStorage', { reason: reason?.code || 'FEATURE_DISABLED' });
    safeLog('info', 'Usando fallback local.', {
        domain,
        source: 'localStorage',
        code: reason?.code || 'FEATURE_DISABLED',
        count: Array.isArray(data) ? data.length : undefined,
    });
    return { data, source: 'localStorage', fallbackReason: reason?.code || null };
}

export async function readDomain({
    domain,
    apiOperation,
    fallbackOperation,
    preferLocalWhenApiEmpty = true,
}) {
    if (!isApiEnabled(domain)) {
        return fallbackResult(domain, fallbackOperation, { code: 'FEATURE_DISABLED' });
    }
    try {
        if (!(await ensureBackendReady())) {
            return fallbackResult(domain, fallbackOperation, { code: 'BACKEND_OFFLINE' });
        }
        const apiData = await apiOperation();
        if (preferLocalWhenApiEmpty && !hasRecords(apiData) && typeof fallbackOperation === 'function') {
            const localData = await fallbackOperation();
            if (hasRecords(localData)) {
                return fallbackResult(domain, () => localData, { code: 'API_EMPTY_LOCAL_PRESENT' });
            }
        }
        setDomainSource(domain, 'api');
        safeLog('info', 'Lectura completada.', {
            domain,
            source: 'api',
            count: Array.isArray(apiData?.items) ? apiData.items.length : undefined,
        });
        return { data: apiData, source: 'api', fallbackReason: null };
    } catch (error) {
        return fallbackResult(domain, fallbackOperation, error);
    }
}

export async function writeDomain({
    domain,
    apiOperation,
    fallbackOperation,
    apiWritesEnabled = true,
    fallbackOnApiError = true,
}) {
    const lastSource = getDomainSource(domain);
    if (lastSource === 'localStorage') {
        return fallbackResult(domain, fallbackOperation, {
            code: 'DOMAIN_USING_LOCAL_FALLBACK',
        });
    }
    const canUseApi = isApiEnabled(domain)
        && apiWritesEnabled;
    if (!canUseApi) {
        throw new DataProviderError(
            'La escritura API de este módulo está desactivada.',
            'API_WRITES_DISABLED',
        );
    }
    try {
        if (!(await ensureBackendReady())) {
            throw new DataProviderError(
                'El backend local no está disponible. No se guardó ningún cambio financiero.',
                'BACKEND_OFFLINE',
            );
        }
        const data = await apiOperation();
        setDomainSource(domain, 'api');
        return { data, source: 'api', fallbackReason: null };
    } catch (error) {
        if (fallbackOnApiError) return fallbackResult(domain, fallbackOperation, error);
        safeLog('warn', 'Escritura API rechazada sin fallback.', {
            domain,
            source: 'api',
            code: error?.code || 'API_WRITE_FAILED',
        });
        throw error;
    }
}

export function normalizeTask(item) {
    return {
        id: item.id,
        text: item.title || '',
        done: item.status === 'done',
        priority: item.priority === 'urgente' ? 'urgente' : 'normal',
        dueDate: item.due_at ? String(item.due_at).slice(0, 10) : '',
        createdAt: item.created_at || '',
        description: item.description || '',
        dataSource: 'api',
    };
}

export function taskPayload(item) {
    return {
        title: item.text,
        description: item.description || '',
        priority: item.priority || 'normal',
        due_at: item.dueDate ? `${item.dueDate}T09:00:00-06:00` : null,
        status: item.done ? 'done' : 'pending',
        source: 'frontend',
        metadata: { legacy_id: item.legacyId || null },
    };
}

export function normalizeEvent(item) {
    const startsAt = new Date(item.starts_at);
    const endsAt = item.ends_at ? new Date(item.ends_at) : null;
    const validStart = !Number.isNaN(startsAt.getTime());
    const metadata = item.metadata || item.details || {};
    return {
        id: item.id,
        date: validStart ? startsAt.toLocaleDateString('en-CA') : '',
        startTime: !item.all_day && validStart
            ? startsAt.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false })
            : '',
        endTime: !item.all_day && endsAt && !Number.isNaN(endsAt.getTime())
            ? endsAt.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false })
            : '',
        title: item.title || '',
        type: metadata.type || 'Evento',
        location: item.location || '',
        notes: item.description || '',
        done: item.status === 'done',
        source: item.source || 'api',
        recurrence: item.recurrence || 'none',
        recurrenceIntervalDays: metadata.recurrenceIntervalDays || '',
        recurrenceUntil: metadata.recurrenceUntil || '',
        dataSource: 'api',
    };
}

export function eventPayload(item) {
    const startsAt = item.startTime
        ? `${item.date}T${item.startTime}:00-06:00`
        : `${item.date}T00:00:00-06:00`;
    const endsAt = item.endTime ? `${item.date}T${item.endTime}:00-06:00` : null;
    return {
        title: item.title,
        description: item.notes || '',
        starts_at: startsAt,
        ends_at: endsAt,
        all_day: !item.startTime,
        recurrence: item.recurrence || 'none',
        location: item.location || '',
        source: 'frontend',
        status: item.done ? 'done' : 'active',
        metadata: {
            type: item.type || 'Evento',
            recurrenceIntervalDays: item.recurrenceIntervalDays || '',
            recurrenceUntil: item.recurrenceUntil || '',
        },
    };
}

export function normalizeTransaction(item) {
    const metadata = item.metadata || item.details || {};
    const amount = item.amount !== undefined
        ? Number(item.amount || 0)
        : Number(item.amount_cents || 0) / 100;
    return {
        ...metadata,
        id: item.id,
        date: item.date,
        type: item.type,
        category: item.category || 'Otro',
        name: item.name || '',
        desc: item.description || '',
        amount,
        expenseNature: item.expense_nature || '',
        source: item.source || 'api',
        sourceHash: item.source_hash || metadata.sourceHash || '',
        dataSource: 'api',
    };
}

export function transactionPayload(item) {
    const metadataFields = [
        'institution',
        'accountType',
        'providerKey',
        'fileName',
        'importBatchId',
        'subscriptionId',
    ];
    const metadata = {};
    metadataFields.forEach((field) => {
        if (item[field] !== undefined && item[field] !== '') metadata[field] = item[field];
    });
    return {
        date: item.date,
        type: item.type,
        category: item.category || 'Otro',
        name: item.name,
        description: item.desc || '',
        amount: Number(item.amount || 0),
        expense_nature: item.expenseNature || '',
        source: ['manual', 'import', 'migration', 'inbox', 'frontend', 'statement'].includes(item.source)
            ? item.source
            : 'frontend',
        account_id: item.accountId || null,
        source_hash: item.sourceHash || null,
        metadata,
    };
}

export function normalizeBudget(item) {
    return {
        id: item.id,
        period: item.period,
        incomeTarget: Number(item.income_target || 0),
        expenseLimit: Number(item.expense_limit || 0),
        savingsTarget: Number(item.savings_target || 0),
        categoryLimits: { ...(item.category_limits || {}) },
        dataSource: 'api',
    };
}

export function budgetPayload(item) {
    return {
        period: item.period,
        income_target: Number(item.incomeTarget || 0),
        expense_limit: Number(item.expenseLimit || 0),
        savings_target: Number(item.savingsTarget || 0),
        category_limits: { ...(item.categoryLimits || {}) },
    };
}

export function normalizeSubscription(item) {
    return {
        id: item.id,
        name: item.name || '',
        amount: Number(item.amount || 0),
        category: item.category || 'Suscripciones',
        day: Number(item.billing_day || 1),
        frequency: item.frequency || 'monthly',
        month: item.billing_month || '',
        paymentMethod: item.payment_method || '',
        active: item.active !== false,
        notes: item.notes || '',
        nextDueDate: item.next_due_date || '',
        dataSource: 'api',
    };
}

export function subscriptionPayload(item) {
    return {
        name: item.name,
        amount: Number(item.amount || 0),
        category: item.category || 'Suscripciones',
        billing_day: Number(item.day || 1),
        frequency: item.frequency || 'monthly',
        billing_month: item.frequency === 'yearly' ? Number(item.month || 1) : null,
        payment_method: item.paymentMethod || '',
        active: item.active !== false,
        notes: item.notes || '',
    };
}

export function normalizeDebt(item) {
    return {
        id: item.id,
        name: item.entity || 'Sin entidad',
        direction: item.direction || 'owed',
        initialAmount: Number(item.initial_amount || 0),
        currentAmount: Number(item.amount || 0),
        minimumPayment: Number(item.minimum_payment || 0),
        institution: item.institution || '',
        debtType: item.debt_type || 'other',
        interestRate: Number(item.interest_rate || 0),
        dueDate: item.due_date || '',
        status: item.status || 'active',
        archived: item.archived === true,
        notes: item.notes || '',
        createdAt: item.created_at || '',
        dataSource: 'api',
    };
}

export function debtPayload(item) {
    return {
        entity: item.name || item.entity,
        direction: item.direction || 'owed',
        amount: Number(item.amount ?? item.currentAmount ?? 0),
        minimum_payment: Number(item.minimumPayment || 0),
        institution: item.institution || '',
        debt_type: item.debtType || 'other',
        interest_rate: Number(item.interestRate || 0),
        due_date: item.dueDate || null,
        status: item.status || 'active',
        notes: item.notes || '',
    };
}

export function debtUpdatePayload(item) {
    const payload = debtPayload(item);
    payload.current_amount = payload.amount;
    delete payload.amount;
    if (item.archived !== undefined) payload.archived = Boolean(item.archived);
    return payload;
}

export function normalizeDebtMovement(item, debtId) {
    return {
        id: item.id,
        entityId: debtId || item.debt_id,
        date: item.date,
        dueDate: item.due_date || '',
        type: item.kind || 'new_debt',
        desc: item.description || '',
        amount: Number(item.amount || 0),
        dataSource: 'api',
    };
}

export function debtMovementPayload(item) {
    return {
        date: item.date,
        kind: item.type || 'new_debt',
        amount: Number(item.amount || 0),
        description: item.desc || '',
        due_date: item.dueDate || null,
    };
}

export function normalizeInvestment(item) {
    const metadata = item.metadata || item.details || {};
    return {
        ...metadata,
        id: item.id,
        type: item.investment_type || 'Otro',
        place: item.institution || 'Sin institución',
        amount: Number(item.amount || 0),
        asOfDate: item.as_of_date || '',
        dataSource: 'api',
    };
}

export function investmentPayload(item) {
    return {
        investment_type: item.type || 'Otro',
        institution: item.place || 'Sin institución',
        amount: Number(item.amount || 0),
        as_of_date: item.asOfDate || null,
        metadata: {},
    };
}

function mexicoDateFromTimestamp(value) {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 10);
    return parsed.toLocaleDateString('en-CA', { timeZone: 'America/Mexico_City' });
}

function stripBridgeFields(item) {
    const {
        dataSource,
        idempotencyKey,
        logType,
        routineType,
        recordedAt,
        ...metadata
    } = item || {};
    return metadata;
}

export function normalizeHealthLog(item) {
    const metadata = item.metadata || item.details || {};
    const date = mexicoDateFromTimestamp(item.recorded_at);
    const base = {
        ...metadata,
        id: item.id,
        logType: item.log_type,
        recordedAt: item.recorded_at,
        date: metadata.date || date,
        value: item.value,
        unit: item.unit || '',
        notes: item.notes || metadata.notes || '',
        dataSource: 'api',
    };
    if (item.log_type === 'body') base.weight = Number(item.value || metadata.weight || 0);
    if (item.log_type === 'wellbeing') {
        base.sleepHours = Number(
            metadata.sleepHours ?? metadata.sleep ?? item.value ?? 0,
        );
    }
    if (item.log_type === 'meal') {
        base.type = metadata.type || 'Comida';
        base.desc = metadata.desc || item.notes || '';
    }
    return base;
}

export function healthLogPayload(item) {
    const logType = item.logType || item.log_type || 'daily_health';
    const date = item.date
        || mexicoDateFromTimestamp(item.recordedAt)
        || new Date().toLocaleDateString('en-CA', { timeZone: 'America/Mexico_City' });
    let value = item.value ?? null;
    let unit = item.unit || '';
    let notes = item.notes || '';
    if (logType === 'body') {
        value = Number(item.weight || 0);
        unit = 'kg';
    } else if (logType === 'wellbeing') {
        value = Number(item.sleepHours ?? item.sleep ?? 0);
        unit = 'hours';
    } else if (logType === 'meal') {
        notes = item.desc || notes;
    } else if (logType === 'daily_health') {
        value = Number(item.water?.current ?? item.value ?? 0);
        unit = 'glasses';
    }
    const metadata = logType === 'daily_health'
        ? {
            date,
            calories: item.calories || {},
            water: item.water || {},
            activity: item.activity || {},
            macros: item.macros || {},
            goals: item.goals || {},
        }
        : { ...stripBridgeFields(item), date };
    return {
        log_type: logType,
        recorded_at: item.recordedAt || `${date}T12:00:00-06:00`,
        value,
        unit,
        notes,
        metadata,
    };
}

export function normalizeRoutine(item) {
    const metadata = item.metadata || item.details || {};
    const schedule = item.schedule || {};
    return {
        ...metadata,
        ...schedule,
        id: item.id,
        routineType: item.routine_type,
        name: item.name || '',
        schedule,
        active: item.active !== false,
        dataSource: 'api',
    };
}

export function routinePayload(item) {
    const routineType = item.routineType || item.routine_type || 'schedule';
    const bridgeFields = new Set([
        'id',
        'routineType',
        'routine_type',
        'name',
        'active',
        'dataSource',
        'idempotencyKey',
        'schedule',
    ]);
    const metadata = Object.fromEntries(
        Object.entries(item || {}).filter(([key]) => !bridgeFields.has(key)),
    );
    const schedule = ['schedule', 'gym', 'cardio'].includes(routineType)
        ? { ...(item.schedule || {}), ...metadata }
        : (item.schedule || {});
    return {
        routine_type: routineType,
        name: item.name || item.text || item.exercise || routineType,
        schedule,
        active: item.active !== false,
        metadata,
    };
}

export function normalizeCarLog(item) {
    const metadata = item.metadata || item.details || {};
    return {
        ...metadata,
        id: item.id,
        logType: item.log_type,
        date: item.date,
        km: Number(item.odometer_km ?? metadata.km ?? metadata.odometerKm ?? 0),
        cost: Number(item.amount || 0),
        notes: metadata.notes || item.description || '',
        dataSource: 'api',
    };
}

export function carLogPayload(item) {
    const logType = item.logType || item.log_type || 'odometer';
    return {
        log_type: logType,
        date: item.date,
        odometer_km: Number(item.km ?? item.odometerKm ?? 0) || null,
        amount: Number(item.cost ?? item.amount ?? 0),
        description: item.notes || item.description || item.type || '',
        metadata: stripBridgeFields(item),
    };
}

export function normalizeCarReminder(item) {
    const metadata = item.metadata || item.details || {};
    return {
        ...metadata,
        id: item.id,
        reminderType: item.reminder_type,
        title: item.title || '',
        dueDate: item.due_date || '',
        dueOdometerKm: item.due_odometer_km,
        recurrence: item.recurrence || 'none',
        status: item.status || 'pending',
        dataSource: 'api',
    };
}

export function carReminderPayload(item) {
    return {
        reminder_type: item.reminderType || item.reminder_type || item.type || 'maintenance',
        title: item.title || item.label || 'Recordatorio del coche',
        due_date: item.dueDate || item.due_date || null,
        due_odometer_km: Number(item.dueOdometerKm ?? item.due_odometer_km ?? 0) || null,
        recurrence: item.recurrence || 'none',
        status: item.status || 'pending',
        metadata: stripBridgeFields(item),
    };
}

export function createIdempotencyKey(prefix = 'frontend') {
    const id = globalThis.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}-${id}`.slice(0, 160);
}

export async function fetchAllPages(path, params = {}, pageSize = 200) {
    const items = [];
    let offset = 0;
    let total = 0;
    do {
        const query = new URLSearchParams({
            ...Object.fromEntries(
                Object.entries(params).filter(([, value]) => (
                    value !== undefined && value !== null && value !== ''
                )),
            ),
            limit: String(pageSize),
            offset: String(offset),
        });
        const page = await apiRequest(`${path}?${query}`);
        const pageItems = Array.isArray(page?.items) ? page.items : [];
        total = Number(page?.total || 0);
        items.push(...pageItems);
        offset += pageItems.length;
        if (!pageItems.length) break;
    } while (items.length < total);
    return items;
}

export function createTransactionApi(item, idempotencyKey) {
    return apiRequest('/api/transactions', {
        method: 'POST',
        headers: {
            'Idempotency-Key': idempotencyKey || createIdempotencyKey('transaction-create'),
        },
        body: transactionPayload(item),
    });
}

export function updateTransactionApi(id, item, idempotencyKey) {
    return apiRequest(`/api/transactions/${id}`, {
        method: 'PUT',
        headers: {
            'Idempotency-Key': idempotencyKey || createIdempotencyKey('transaction-update'),
        },
        body: transactionPayload(item),
    });
}

export function deleteTransactionApi(id, idempotencyKey) {
    return apiRequest(`/api/transactions/${id}`, {
        method: 'DELETE',
        headers: {
            'Idempotency-Key': idempotencyKey || createIdempotencyKey('transaction-delete'),
        },
    });
}

export function restoreTransactionApi(id, idempotencyKey) {
    return apiRequest(`/api/transactions/${id}/restore`, {
        method: 'POST',
        headers: {
            'Idempotency-Key': idempotencyKey || createIdempotencyKey('transaction-restore'),
        },
    });
}

export const summaryProvider = {
    today: (fallback) => readDomain({
        domain: 'summary',
        apiOperation: () => apiRequest('/api/summary/today'),
        fallbackOperation: fallback,
    }),
    week: (fallback) => readDomain({
        domain: 'summary',
        apiOperation: () => apiRequest('/api/summary/week'),
        fallbackOperation: fallback,
    }),
    month: (fallback) => readDomain({
        domain: 'summary',
        apiOperation: () => apiRequest('/api/summary/month'),
        fallbackOperation: fallback,
    }),
};

export const taskProvider = {
    getTasks: (fallback) => readDomain({
        domain: 'tasks',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/tasks');
            return items.map(normalizeTask);
        },
        fallbackOperation: fallback,
    }),
    createTask: (item, fallback) => writeDomain({
        domain: 'tasks',
        apiOperation: async () => normalizeTask(await apiRequest('/api/tasks', {
            method: 'POST',
            body: taskPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateTask: (id, item, fallback) => writeDomain({
        domain: 'tasks',
        apiOperation: async () => normalizeTask(await apiRequest(`/api/tasks/${id}`, {
            method: 'PUT',
            body: taskPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteTask: (id, fallback) => writeDomain({
        domain: 'tasks',
        apiOperation: () => apiRequest(`/api/tasks/${id}`, { method: 'DELETE' }),
        fallbackOperation: fallback,
    }),
};

export const eventProvider = {
    getEvents: (fallback) => readDomain({
        domain: 'events',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/events');
            return items.map(normalizeEvent);
        },
        fallbackOperation: fallback,
    }),
    createEvent: (item, fallback) => writeDomain({
        domain: 'events',
        apiOperation: async () => normalizeEvent(await apiRequest('/api/events', {
            method: 'POST',
            body: eventPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateEvent: (id, item, fallback) => writeDomain({
        domain: 'events',
        apiOperation: async () => normalizeEvent(await apiRequest(`/api/events/${id}`, {
            method: 'PUT',
            body: eventPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteEvent: (id, fallback) => writeDomain({
        domain: 'events',
        apiOperation: () => apiRequest(`/api/events/${id}`, { method: 'DELETE' }),
        fallbackOperation: fallback,
    }),
};

export const transactionProvider = {
    getTransactions: (filters = {}, fallback) => readDomain({
        domain: 'transactions',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/transactions', filters);
            return items.map(normalizeTransaction);
        },
        fallbackOperation: fallback,
    }),
    createTransaction: (item, fallback) => writeDomain({
        domain: 'transactions',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForTransactionWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeTransaction(await createTransactionApi(
            item,
            item.idempotencyKey,
        )),
        fallbackOperation: fallback,
    }),
    updateTransaction: (id, item, fallback) => writeDomain({
        domain: 'transactions',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForTransactionWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeTransaction(await updateTransactionApi(
            id,
            item,
            item.idempotencyKey,
        )),
        fallbackOperation: fallback,
    }),
    deleteTransaction: (id, fallback) => writeDomain({
        domain: 'transactions',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForTransactionWrites,
        fallbackOnApiError: false,
        apiOperation: () => deleteTransactionApi(id),
        fallbackOperation: fallback,
    }),
    restoreTransaction: (id) => writeDomain({
        domain: 'transactions',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForTransactionWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeTransaction(await restoreTransactionApi(id)),
    }),
};

export const budgetProvider = {
    getBudgets: (fallback) => readDomain({
        domain: 'budgets',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/budgets');
            return items.map(normalizeBudget);
        },
        fallbackOperation: fallback,
    }),
    saveBudget: (item, fallback) => writeDomain({
        domain: 'budgets',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForBudgetWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeBudget(await apiRequest(
            item.id ? `/api/budgets/${item.id}` : '/api/budgets',
            {
                method: item.id ? 'PUT' : 'POST',
                body: budgetPayload(item),
            },
        )),
        fallbackOperation: fallback,
    }),
    deleteBudget: (id, fallback) => writeDomain({
        domain: 'budgets',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForBudgetWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/budgets/${id}`, { method: 'DELETE' }),
        fallbackOperation: fallback,
    }),
};

export const subscriptionProvider = {
    getSubscriptions: (fallback) => readDomain({
        domain: 'subscriptions',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/subscriptions');
            return items.map(normalizeSubscription);
        },
        fallbackOperation: fallback,
    }),
    createSubscription: (item, fallback) => writeDomain({
        domain: 'subscriptions',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForSubscriptionWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeSubscription(await apiRequest('/api/subscriptions', {
            method: 'POST',
            body: subscriptionPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateSubscription: (id, item, fallback) => writeDomain({
        domain: 'subscriptions',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForSubscriptionWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeSubscription(await apiRequest(`/api/subscriptions/${id}`, {
            method: 'PUT',
            body: subscriptionPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteSubscription: (id, fallback) => writeDomain({
        domain: 'subscriptions',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForSubscriptionWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/subscriptions/${id}`, { method: 'DELETE' }),
        fallbackOperation: fallback,
    }),
};

export const debtProvider = {
    getDebts: (fallback) => readDomain({
        domain: 'debts',
        apiOperation: async () => {
            const debtItems = await fetchAllPages('/api/debts', { include_archived: true });
            const entities = debtItems.map(normalizeDebt);
            const movementPages = await Promise.all(entities.map((entity) => (
                fetchAllPages(`/api/debts/${entity.id}/movements`)
            )));
            const transactions = movementPages.flatMap((movements, index) => (
                movements.map((item) => normalizeDebtMovement(item, entities[index].id))
            ));
            return { entities, transactions };
        },
        fallbackOperation: fallback,
    }),
    createDebt: (item, fallback) => writeDomain({
        domain: 'debts',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForDebtWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeDebt(await apiRequest('/api/debts', {
            method: 'POST',
            body: debtPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateDebt: (id, item, fallback) => writeDomain({
        domain: 'debts',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForDebtWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeDebt(await apiRequest(`/api/debts/${id}`, {
            method: 'PUT',
            body: debtUpdatePayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteDebt: (id, fallback) => writeDomain({
        domain: 'debts',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForDebtWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/debts/${id}`, { method: 'DELETE' }),
        fallbackOperation: fallback,
    }),
    addMovement: (debtId, item, fallback) => writeDomain({
        domain: 'debts',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForDebtWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeDebtMovement(
            await apiRequest(`/api/debts/${debtId}/movements`, {
                method: 'POST',
                body: debtMovementPayload(item),
            }),
            debtId,
        ),
        fallbackOperation: fallback,
    }),
    deleteMovement: (debtId, movementId, fallback) => writeDomain({
        domain: 'debts',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForDebtWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/debts/${debtId}/movements/${movementId}`, {
            method: 'DELETE',
        }),
        fallbackOperation: fallback,
    }),
};

export const investmentProvider = {
    getInvestments: (fallback) => readDomain({
        domain: 'investments',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/investments');
            return items.map(normalizeInvestment);
        },
        fallbackOperation: fallback,
    }),
    createInvestment: (item, fallback) => writeDomain({
        domain: 'investments',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForInvestmentWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeInvestment(await apiRequest('/api/investments', {
            method: 'POST',
            body: investmentPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateInvestment: (id, item, fallback) => writeDomain({
        domain: 'investments',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForInvestmentWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeInvestment(await apiRequest(`/api/investments/${id}`, {
            method: 'PUT',
            body: investmentPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteInvestment: (id, fallback) => writeDomain({
        domain: 'investments',
        apiWritesEnabled: FINANCE_WRITE_FLAGS.useApiForInvestmentWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/investments/${id}`, { method: 'DELETE' }),
        fallbackOperation: fallback,
    }),
};

export const healthProvider = {
    getHealthLogs: (filters = {}, fallback) => readDomain({
        domain: 'health',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/health/logs', filters);
            return items.map(normalizeHealthLog);
        },
        fallbackOperation: fallback,
    }),
    createHealthLog: (item, fallback) => writeDomain({
        domain: 'health',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForHealthWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeHealthLog(await apiRequest('/api/health/logs', {
            method: 'POST',
            headers: {
                'Idempotency-Key': item.idempotencyKey
                    || createIdempotencyKey('health-create'),
            },
            body: healthLogPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateHealthLog: (id, item, fallback) => writeDomain({
        domain: 'health',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForHealthWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeHealthLog(await apiRequest(`/api/health/logs/${id}`, {
            method: 'PUT',
            headers: {
                'Idempotency-Key': item.idempotencyKey
                    || createIdempotencyKey('health-update'),
            },
            body: healthLogPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteHealthLog: (id, fallback) => writeDomain({
        domain: 'health',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForHealthWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/health/logs/${id}`, {
            method: 'DELETE',
            headers: {
                'Idempotency-Key': createIdempotencyKey('health-delete'),
            },
        }),
        fallbackOperation: fallback,
    }),
    getHealthStats: (filters = {}, fallback) => readDomain({
        domain: 'health',
        apiOperation: () => {
            const query = new URLSearchParams(
                Object.fromEntries(
                    Object.entries(filters).filter(([, value]) => (
                        value !== undefined && value !== null && value !== ''
                    )),
                ),
            );
            return apiRequest(`/api/health/stats?${query}`);
        },
        fallbackOperation: fallback,
        preferLocalWhenApiEmpty: false,
    }),
};

export const routineProvider = {
    getRoutines: (filters = {}, fallback) => readDomain({
        domain: 'routines',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/routines', filters);
            return items.map(normalizeRoutine);
        },
        fallbackOperation: fallback,
    }),
    createRoutine: (item, fallback) => writeDomain({
        domain: 'routines',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForRoutineWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeRoutine(await apiRequest('/api/routines', {
            method: 'POST',
            headers: {
                'Idempotency-Key': item.idempotencyKey
                    || createIdempotencyKey('routine-create'),
            },
            body: routinePayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateRoutine: (id, item, fallback) => writeDomain({
        domain: 'routines',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForRoutineWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeRoutine(await apiRequest(`/api/routines/${id}`, {
            method: 'PUT',
            headers: {
                'Idempotency-Key': item.idempotencyKey
                    || createIdempotencyKey('routine-update'),
            },
            body: routinePayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteRoutine: (id, fallback) => writeDomain({
        domain: 'routines',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForRoutineWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/routines/${id}`, {
            method: 'DELETE',
            headers: {
                'Idempotency-Key': createIdempotencyKey('routine-delete'),
            },
        }),
        fallbackOperation: fallback,
    }),
};

export const carProvider = {
    getCarBundle: (fallback) => readDomain({
        domain: 'car',
        apiOperation: async () => {
            const [logs, reminders, summary] = await Promise.all([
                fetchAllPages('/api/car/logs'),
                fetchAllPages('/api/car/reminders'),
                apiRequest('/api/car/summary'),
            ]);
            return {
                logs: logs.map(normalizeCarLog),
                reminders: reminders.map(normalizeCarReminder),
                summary,
            };
        },
        fallbackOperation: fallback,
    }),
    getCarLogs: (filters = {}, fallback) => readDomain({
        domain: 'car',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/car/logs', filters);
            return items.map(normalizeCarLog);
        },
        fallbackOperation: fallback,
    }),
    createCarLog: (item, fallback) => writeDomain({
        domain: 'car',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeCarLog(await apiRequest('/api/car/logs', {
            method: 'POST',
            headers: {
                'Idempotency-Key': item.idempotencyKey || createIdempotencyKey('car-log-create'),
            },
            body: carLogPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateCarLog: (id, item, fallback) => writeDomain({
        domain: 'car',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeCarLog(await apiRequest(`/api/car/logs/${id}`, {
            method: 'PUT',
            headers: {
                'Idempotency-Key': item.idempotencyKey || createIdempotencyKey('car-log-update'),
            },
            body: carLogPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    deleteCarLog: (id, fallback) => writeDomain({
        domain: 'car',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/car/logs/${id}`, {
            method: 'DELETE',
            headers: {
                'Idempotency-Key': createIdempotencyKey('car-log-delete'),
            },
        }),
        fallbackOperation: fallback,
    }),
    getCarReminders: (filters = {}, fallback) => readDomain({
        domain: 'car',
        apiOperation: async () => {
            const items = await fetchAllPages('/api/car/reminders', filters);
            return items.map(normalizeCarReminder);
        },
        fallbackOperation: fallback,
    }),
    createCarReminder: (item, fallback) => writeDomain({
        domain: 'car',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeCarReminder(await apiRequest('/api/car/reminders', {
            method: 'POST',
            headers: {
                'Idempotency-Key': item.idempotencyKey
                    || createIdempotencyKey('car-reminder-create'),
            },
            body: carReminderPayload(item),
        })),
        fallbackOperation: fallback,
    }),
    updateCarReminder: (id, item, fallback) => writeDomain({
        domain: 'car',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites,
        fallbackOnApiError: false,
        apiOperation: async () => normalizeCarReminder(
            await apiRequest(`/api/car/reminders/${id}`, {
                method: 'PUT',
                headers: {
                    'Idempotency-Key': item.idempotencyKey
                        || createIdempotencyKey('car-reminder-update'),
                },
                body: carReminderPayload(item),
            }),
        ),
        fallbackOperation: fallback,
    }),
    deleteCarReminder: (id, fallback) => writeDomain({
        domain: 'car',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest(`/api/car/reminders/${id}`, {
            method: 'DELETE',
            headers: {
                'Idempotency-Key': createIdempotencyKey('car-reminder-delete'),
            },
        }),
        fallbackOperation: fallback,
    }),
    getCarSummary: (fallback) => readDomain({
        domain: 'car',
        apiOperation: () => apiRequest('/api/car/summary'),
        fallbackOperation: fallback,
        preferLocalWhenApiEmpty: false,
    }),
    updateCarProfile: (profile, fallback) => writeDomain({
        domain: 'car',
        apiWritesEnabled: HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites,
        fallbackOnApiError: false,
        apiOperation: () => apiRequest('/api/car/profile', {
            method: 'PUT',
            headers: {
                'Idempotency-Key': createIdempotencyKey('car-profile-update'),
            },
            body: profile,
        }),
        fallbackOperation: fallback,
    }),
};

export const dataProvider = {
    createIdempotencyKey,
    getDomainSource,
    readLegacyState,
    writeLegacyState,
    summary: summaryProvider,
    tasks: taskProvider,
    events: eventProvider,
    transactions: transactionProvider,
    budgets: budgetProvider,
    subscriptions: subscriptionProvider,
    debts: debtProvider,
    investments: investmentProvider,
    health: healthProvider,
    routines: routineProvider,
    car: carProvider,
};
