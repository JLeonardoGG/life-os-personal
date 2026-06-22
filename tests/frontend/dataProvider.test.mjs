import assert from 'node:assert/strict';
import test from 'node:test';

const storage = new Map();
globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
};
globalThis.window = {
    dispatchEvent: () => {},
};
globalThis.CustomEvent = class {
    constructor(type, options) {
        this.type = type;
        this.detail = options.detail;
    }
};

const {
    createIdempotencyKey,
    createTransactionApi,
    eventPayload,
    fetchAllPages,
    getDomainSource,
    budgetPayload,
    debtMovementPayload,
    debtPayload,
    normalizeBudget,
    normalizeDebt,
    normalizeDebtMovement,
    normalizeEvent,
    normalizeHealthLog,
    normalizeInvestment,
    normalizeRoutine,
    normalizeCarLog,
    normalizeCarReminder,
    normalizeTask,
    normalizeTransaction,
    normalizeSubscription,
    readDomain,
    readLegacyState,
    taskPayload,
    subscriptionPayload,
    transactionPayload,
    investmentPayload,
    healthLogPayload,
    routinePayload,
    carLogPayload,
    carReminderPayload,
    writeDomain,
} = await import('../../frontend/assets/js/core/dataProvider.js');

test('readLegacyState reads the existing Life OS state', () => {
    storage.set('lifeos_data_v2', JSON.stringify({ todos: [{ id: 1 }] }));
    assert.equal(readLegacyState().todos.length, 1);
});

test('disabled domains use localStorage fallback without mixing sources', async () => {
    const result = await readDomain({
        domain: 'tax',
        apiOperation: async () => [{ id: 'api' }],
        fallbackOperation: () => [{ id: 'local' }],
    });
    assert.equal(result.source, 'localStorage');
    assert.deepEqual(result.data, [{ id: 'local' }]);
    assert.equal(getDomainSource('tax'), 'localStorage');
});

test('task adapter preserves editable frontend fields', () => {
    const task = normalizeTask({
        id: 'task-1',
        title: 'Pagar tarjeta',
        status: 'done',
        priority: 'urgente',
        due_at: '2026-06-23T09:00:00-06:00',
        description: 'Revisar saldo',
    });
    assert.deepEqual(taskPayload(task), {
        title: 'Pagar tarjeta',
        description: 'Revisar saldo',
        priority: 'urgente',
        due_at: '2026-06-23T09:00:00-06:00',
        status: 'done',
        source: 'frontend',
        metadata: { legacy_id: null },
    });
});

test('event adapter reads backend details and builds an API payload', () => {
    const event = normalizeEvent({
        id: 'event-1',
        title: 'Cita',
        description: 'Llevar documentos',
        starts_at: '2026-06-24T10:00:00-06:00',
        ends_at: '2026-06-24T11:00:00-06:00',
        all_day: false,
        recurrence: 'weekly',
        location: 'Oficina',
        status: 'active',
        source: 'frontend',
        details: {
            type: 'Personal',
            recurrenceUntil: '2026-08-01',
        },
    });
    assert.equal(event.type, 'Personal');
    assert.equal(event.recurrenceUntil, '2026-08-01');
    assert.equal(eventPayload(event).title, 'Cita');
    assert.equal(eventPayload(event).metadata.type, 'Personal');
});

test('transaction adapter keeps API pesos and supports raw cents defensively', () => {
    const serialized = normalizeTransaction({
        id: 'tx-1',
        date: '2026-06-22',
        type: 'gasto',
        category: 'Transporte',
        name: 'Gasolina',
        amount: 845.5,
        expense_nature: 'corriente',
        details: { institution: 'Demo Bank' },
    });
    const raw = normalizeTransaction({
        id: 'tx-2',
        date: '2026-06-22',
        type: 'ingreso',
        name: 'Ingreso',
        amount_cents: 12345,
    });
    assert.equal(serialized.amount, 845.5);
    assert.equal(serialized.institution, 'Demo Bank');
    assert.equal(raw.amount, 123.45);
});

test('transaction payload keeps source, account and sanitized import metadata', () => {
    const payload = transactionPayload({
        date: '2026-06-22',
        type: 'gasto',
        category: 'Comida',
        name: 'Despensa',
        amount: 250.75,
        source: 'statement',
        sourceHash: 'statement-demo-hash',
        accountId: 'account-1',
        institution: 'Banco demo',
        fileName: 'demo.csv',
    });
    assert.equal(payload.amount, 250.75);
    assert.equal(payload.source, 'statement');
    assert.equal(payload.source_hash, 'statement-demo-hash');
    assert.equal(payload.account_id, 'account-1');
    assert.deepEqual(payload.metadata, {
        institution: 'Banco demo',
        fileName: 'demo.csv',
    });
});

test('financial API write errors do not silently fall back to localStorage', async () => {
    let fallbackCalled = false;
    await assert.rejects(
        writeDomain({
            domain: 'transactions',
            apiWritesEnabled: false,
            fallbackOnApiError: false,
            apiOperation: async () => ({ id: 'api' }),
            fallbackOperation: () => {
                fallbackCalled = true;
                return { id: 'local' };
            },
        }),
        (error) => error.code === 'API_WRITES_DISABLED',
    );
    assert.equal(fallbackCalled, false);
});

test('transaction API wrapper sends an idempotency key', async () => {
    const originalFetch = globalThis.fetch;
    let request;
    globalThis.fetch = async (url, options) => {
        request = { url, options };
        return new Response(JSON.stringify({
            id: 'tx-api',
            date: '2026-06-22',
            type: 'gasto',
            name: 'Demo',
            amount: 10,
        }), {
            status: 201,
            headers: { 'content-type': 'application/json' },
        });
    };
    try {
        const key = createIdempotencyKey('test-transaction');
        await createTransactionApi({
            date: '2026-06-22',
            type: 'gasto',
            name: 'Demo',
            amount: 10,
        }, key);
        assert.equal(request.options.headers['Idempotency-Key'], key);
        assert.equal(request.options.method, 'POST');
    } finally {
        globalThis.fetch = originalFetch;
    }
});

test('budget adapter preserves pesos and monthly category limits', () => {
    const budget = normalizeBudget({
        id: 'budget-1',
        period: '2026-07',
        income_target: 35000.25,
        expense_limit: 10000,
        savings_target: 20000,
        category_limits: { Comida: 2500.5 },
    });
    assert.equal(budget.incomeTarget, 35000.25);
    assert.deepEqual(budgetPayload(budget), {
        period: '2026-07',
        income_target: 35000.25,
        expense_limit: 10000,
        savings_target: 20000,
        category_limits: { Comida: 2500.5 },
    });
});

test('subscription adapter maps billing fields without creating charges', () => {
    const subscription = normalizeSubscription({
        id: 'subscription-1',
        name: 'Internet',
        amount: 599.9,
        category: 'Servicios',
        billing_day: 15,
        frequency: 'monthly',
        billing_month: null,
        payment_method: 'Tarjeta',
        active: true,
        next_due_date: '2026-07-15',
    });
    assert.equal(subscription.day, 15);
    assert.equal(subscription.nextDueDate, '2026-07-15');
    assert.equal(subscriptionPayload(subscription).amount, 599.9);
    assert.equal(subscriptionPayload(subscription).billing_month, null);
});

test('debt adapters preserve positive balances, direction and movement meaning', () => {
    const debt = normalizeDebt({
        id: 'debt-1',
        entity: 'Banco demo',
        direction: 'owed',
        initial_amount: 10000,
        amount: 7500.25,
        minimum_payment: 500,
        debt_type: 'credit_card',
        interest_rate: 42.5,
        due_date: '2026-07-15',
    });
    const movement = normalizeDebtMovement({
        id: 'movement-1',
        date: '2026-06-22',
        kind: 'debt_payment',
        amount: 500.25,
        description: 'Pago',
    }, debt.id);
    assert.equal(debt.currentAmount, 7500.25);
    assert.equal(debt.minimumPayment, 500);
    assert.equal(debt.interestRate, 42.5);
    assert.equal(movement.entityId, debt.id);
    assert.equal(movement.type, 'debt_payment');
    assert.equal(debtMovementPayload(movement).amount, 500.25);
    assert.equal(debtPayload({ ...debt, amount: 0 }).direction, 'owed');
});

test('investment adapter maps API records without external pricing', () => {
    const investment = normalizeInvestment({
        id: 'investment-1',
        investment_type: 'Renta fija',
        institution: 'Institución demo',
        amount: 15000.75,
        as_of_date: '2026-06-22',
    });
    assert.equal(investment.place, 'Institución demo');
    assert.equal(investment.amount, 15000.75);
    assert.deepEqual(investmentPayload(investment), {
        investment_type: 'Renta fija',
        institution: 'Institución demo',
        amount: 15000.75,
        as_of_date: '2026-06-22',
        metadata: {},
    });
});

test('fetchAllPages reads beyond the old 500 record assumption', async () => {
    const originalFetch = globalThis.fetch;
    const offsets = [];
    globalThis.fetch = async (url) => {
        const parsed = new URL(url);
        const offset = Number(parsed.searchParams.get('offset') || 0);
        const limit = Number(parsed.searchParams.get('limit') || 0);
        offsets.push(offset);
        const total = 505;
        const count = Math.min(limit, total - offset);
        const items = Array.from({ length: Math.max(0, count) }, (_, index) => ({
            id: offset + index,
        }));
        return new Response(JSON.stringify({ items, total, limit, offset }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        });
    };
    try {
        const items = await fetchAllPages('/api/transactions', { category: 'Demo' }, 200);
        assert.equal(items.length, 505);
        assert.deepEqual(offsets, [0, 200, 400]);
    } finally {
        globalThis.fetch = originalFetch;
    }
});

test('health adapters preserve Mexico City dates and legacy body fields', () => {
    const healthLog = normalizeHealthLog({
        id: 'health-1',
        log_type: 'body',
        recorded_at: '2026-06-23T00:30:00+00:00',
        value: 82.5,
        unit: 'kg',
        details: { waist: 90 },
    });
    assert.equal(healthLog.date, '2026-06-22');
    assert.equal(healthLog.weight, 82.5);
    assert.equal(healthLog.waist, 90);
    const payload = healthLogPayload({
        logType: 'wellbeing',
        date: '2026-06-22',
        sleepHours: 7.5,
        mood: 4,
    });
    assert.equal(payload.value, 7.5);
    assert.equal(payload.unit, 'hours');
    assert.equal(payload.recorded_at, '2026-06-22T12:00:00-06:00');
    const daily = healthLogPayload({
        logType: 'daily_health',
        date: '2026-06-22',
        water: { current: 6 },
        calories: { current: 1800 },
        bodyRecords: [{ weight: 82.5 }],
    });
    assert.equal(daily.metadata.water.current, 6);
    assert.equal('bodyRecords' in daily.metadata, false);
});

test('routine adapters preserve schedule, gym and cardio metadata', () => {
    const routine = normalizeRoutine({
        id: 'routine-1',
        routine_type: 'gym',
        name: 'Sentadilla',
        schedule: { week: '2026-W26', weight: 80 },
        details: { notes: 'Demo' },
        active: true,
    });
    assert.equal(routine.routineType, 'gym');
    assert.equal(routine.week, '2026-W26');
    assert.equal(routine.weight, 80);
    assert.equal(routinePayload(routine).routine_type, 'gym');
});

test('car adapters preserve odometer, money and reminder fields', () => {
    const log = normalizeCarLog({
        id: 'car-log-1',
        log_type: 'service',
        date: '2026-06-22',
        odometer_km: 50000,
        amount: 2500.5,
        description: 'Servicio',
        details: { shop: 'Taller demo' },
    });
    assert.equal(log.km, 50000);
    assert.equal(log.cost, 2500.5);
    assert.equal(carLogPayload(log).odometer_km, 50000);

    const reminder = normalizeCarReminder({
        id: 'reminder-1',
        reminder_type: 'seguro',
        title: 'Seguro',
        due_date: '2027-03-01',
        recurrence: 'yearly',
        status: 'pending',
    });
    assert.equal(reminder.dueDate, '2027-03-01');
    assert.equal(carReminderPayload(reminder).reminder_type, 'seguro');
});

test('health and car API write flags are disabled by default', async () => {
    const { HEALTH_CAR_WRITE_FLAGS } = await import(
        '../../frontend/assets/js/core/featureFlags.js'
    );
    assert.equal(HEALTH_CAR_WRITE_FLAGS.useApiForHealthWrites, false);
    assert.equal(HEALTH_CAR_WRITE_FLAGS.useApiForRoutineWrites, false);
    assert.equal(HEALTH_CAR_WRITE_FLAGS.useApiForCarWrites, false);
});
