import assert from 'node:assert/strict';
import test from 'node:test';

import { buildFinanceParityReport } from '../../frontend/assets/js/domains/financeParity.js';

const apiRows = [
    {
        id: 'api-1',
        date: '2026-06-01',
        type: 'ingreso',
        category: 'Salario',
        amount: 5000,
        account_id: 'account-1',
    },
    {
        id: 'api-2',
        date: '2026-06-02',
        type: 'gasto',
        category: 'Transporte',
        amount: 180.5,
        account_id: 'account-1',
    },
];

test('finance parity accepts equivalent monthly totals and dimensions', () => {
    const localRows = [
        { ...apiRows[0], id: 1, accountId: 'account-1' },
        { ...apiRows[1], id: 2, accountId: 'account-1' },
    ];
    const report = buildFinanceParityReport(apiRows, localRows, { period: '2026-06' });
    assert.equal(report.isMatch, true);
    assert.equal(report.api.balance, 4819.5);
    assert.equal(report.differences.length, 0);
});

test('finance parity reports only aggregate differences', () => {
    const report = buildFinanceParityReport(apiRows, [apiRows[0]], { period: '2026-06' });
    assert.equal(report.isMatch, false);
    assert.ok(report.differences.some((item) => item.metric === 'count'));
    assert.ok(report.differences.some((item) => item.metric === 'expense'));
    assert.equal(JSON.stringify(report).includes('Transporte'), true);
    assert.equal(JSON.stringify(report).includes('description'), false);
});
