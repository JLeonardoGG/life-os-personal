function roundMoney(value) {
    return Math.round(Number(value || 0) * 100) / 100;
}

function monthOf(item) {
    return String(item.date || '').slice(0, 7);
}

function canonicalType(value) {
    const aliases = {
        income: 'ingreso',
        expense: 'gasto',
        transfer: 'transferencia',
        adjustment: 'ajuste',
    };
    return aliases[value] || value;
}

function summarizeTransactions(items, period) {
    const rows = (items || []).filter((item) => !period || monthOf(item) === period);
    const byCategory = {};
    const byAccount = {};
    let income = 0;
    let expense = 0;

    rows.forEach((item) => {
        const type = canonicalType(item.type);
        const amount = Number(item.amount || 0);
        if (type === 'ingreso') income += amount;
        if (type === 'gasto') expense += amount;
        const category = item.category || 'Sin categoría';
        byCategory[category] = byCategory[category] || { count: 0, amount: 0 };
        byCategory[category].count += 1;
        byCategory[category].amount = roundMoney(byCategory[category].amount + amount);
        const account = item.accountId || item.account_id || 'Sin cuenta';
        byAccount[account] = (byAccount[account] || 0) + 1;
    });

    return {
        count: rows.length,
        income: roundMoney(income),
        expense: roundMoney(expense),
        balance: roundMoney(income - expense),
        byCategory,
        byAccount,
    };
}

function summarizeDebts(items) {
    return (items || []).reduce((summary, item) => {
        const amount = Number(item.amount ?? item.currentAmount ?? item.current_amount ?? 0);
        summary.count += 1;
        if (item.direction === 'receivable') summary.receivable = roundMoney(summary.receivable + amount);
        else summary.owed = roundMoney(summary.owed + amount);
        return summary;
    }, { count: 0, owed: 0, receivable: 0 });
}

function summarizeSubscriptions(items) {
    return (items || []).reduce((summary, item) => {
        if (item.active === false) return summary;
        summary.count += 1;
        summary.total = roundMoney(summary.total + Number(item.amount || 0));
        return summary;
    }, { count: 0, total: 0 });
}

function sameJson(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
}

export function buildFinanceParityReport(apiTransactions, localTransactions, options = {}) {
    const period = options.period || '';
    const api = summarizeTransactions(apiTransactions, period);
    const local = summarizeTransactions(localTransactions, period);
    const differences = [];

    ['count', 'income', 'expense', 'balance'].forEach((metric) => {
        if (api[metric] !== local[metric]) {
            differences.push({ section: 'transactions', metric, api: api[metric], local: local[metric] });
        }
    });
    if (!sameJson(api.byCategory, local.byCategory)) {
        differences.push({
            section: 'transactions',
            metric: 'categories',
            api: Object.keys(api.byCategory).length,
            local: Object.keys(local.byCategory).length,
        });
    }
    if (!sameJson(api.byAccount, local.byAccount)) {
        differences.push({
            section: 'transactions',
            metric: 'accounts',
            api: Object.keys(api.byAccount).length,
            local: Object.keys(local.byAccount).length,
        });
    }

    const apiDebts = summarizeDebts(options.apiDebts);
    const localDebts = summarizeDebts(options.localDebts);
    if ((options.apiDebts || options.localDebts) && !sameJson(apiDebts, localDebts)) {
        differences.push({ section: 'debts', metric: 'summary', api: apiDebts, local: localDebts });
    }

    const apiSubscriptions = summarizeSubscriptions(options.apiSubscriptions);
    const localSubscriptions = summarizeSubscriptions(options.localSubscriptions);
    if (
        (options.apiSubscriptions || options.localSubscriptions)
        && !sameJson(apiSubscriptions, localSubscriptions)
    ) {
        differences.push({
            section: 'subscriptions',
            metric: 'summary',
            api: apiSubscriptions,
            local: localSubscriptions,
        });
    }

    return {
        period,
        isMatch: differences.length === 0,
        checkedAt: new Date().toISOString(),
        api,
        local,
        apiDebts,
        localDebts,
        apiSubscriptions,
        localSubscriptions,
        differences,
    };
}

export const financeParity = {
    buildReport: buildFinanceParityReport,
};
