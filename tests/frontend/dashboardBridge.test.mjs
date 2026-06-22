import assert from 'node:assert/strict';
import test from 'node:test';

import { buildLocalSummary } from '../../frontend/assets/js/domains/dashboardBridge.js';

test('buildLocalSummary calculates local monthly totals in pesos', () => {
    const state = {
        movements: [
            { date: '2026-06-01', type: 'ingreso', amount: 1000 },
            { date: '2026-06-02', type: 'gasto', amount: 180 },
            { date: '2026-05-31', type: 'gasto', amount: 999 },
        ],
        todos: [
            { done: false, dueDate: '2026-06-20', priority: 'urgente' },
            { done: true, dueDate: '2026-06-20', priority: 'normal' },
        ],
        calendar: { events: [{ date: '2026-06-21', done: false }] },
    };
    const result = buildLocalSummary(state, 'month', new Date('2026-06-21T12:00:00-06:00'));
    assert.equal(result.finance.income, 1000);
    assert.equal(result.finance.expense, 180);
    assert.equal(result.finance.balance, 820);
    assert.equal(result.tasks.urgent_count, 1);
    assert.equal(result.events.count, 1);
});
