import { summaryProvider } from '../core/dataProvider.js';

function localDateKey(date) {
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function dateRange(period, now = new Date()) {
    const current = new Date(now);
    const today = localDateKey(current);
    if (period === 'today') return { start: today, end: today };
    if (period === 'week') {
        const day = current.getDay() || 7;
        const start = new Date(current);
        start.setDate(current.getDate() - day + 1);
        const end = new Date(start);
        end.setDate(start.getDate() + 6);
        return { start: localDateKey(start), end: localDateKey(end) };
    }
    const start = new Date(current.getFullYear(), current.getMonth(), 1);
    const end = new Date(current.getFullYear(), current.getMonth() + 1, 0);
    return { start: localDateKey(start), end: localDateKey(end) };
}

export function buildLocalSummary(state, period, now = new Date()) {
    const range = dateRange(period, now);
    const movements = (state.movements || []).filter(
        (item) => item.date >= range.start && item.date <= range.end,
    );
    const income = movements
        .filter((item) => item.type === 'ingreso')
        .reduce((sum, item) => sum + Number(item.amount || 0), 0);
    const expense = movements
        .filter((item) => item.type === 'gasto')
        .reduce((sum, item) => sum + Number(item.amount || 0), 0);
    const tasks = (state.todos || []).filter((item) => {
        if (item.done) return false;
        return !item.dueDate || item.dueDate <= range.end;
    });
    const events = (state.calendar?.events || []).filter(
        (item) => item.date >= range.start && item.date <= range.end && !item.done,
    );
    return {
        period: range,
        finance: {
            income,
            expense,
            balance: income - expense,
            transaction_count: movements.length,
        },
        tasks: {
            open_due_count: tasks.length,
            urgent_count: tasks.filter((item) => item.priority === 'urgente').length,
            items: tasks.slice(0, 10),
        },
        events: {
            count: events.length,
            items: events.slice(0, 10),
        },
    };
}

export async function loadDashboardSummaries(state, now = new Date()) {
    const periods = ['today', 'week', 'month'];
    const results = await Promise.all(periods.map((period) => (
        summaryProvider[period](() => buildLocalSummary(state, period, now))
    )));
    return {
        today: results[0].data,
        week: results[1].data,
        month: results[2].data,
        source: results.every((item) => item.source === 'api') ? 'api' : 'localStorage',
        sources: {
            today: results[0].source,
            week: results[1].source,
            month: results[2].source,
        },
    };
}

function money(value) {
    return `$${Number(value || 0).toLocaleString('es-MX', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
}

export function renderDashboardSummaryBridge(result) {
    const source = document.getElementById('dashboard-data-source');
    if (source) {
        const fromApi = result.source === 'api';
        source.textContent = fromApi ? 'Resumen desde SQLite' : 'Resumen desde localStorage fallback';
        source.className = fromApi
            ? 'dark-chip rounded-full px-3 py-1 text-xs text-emerald-300'
            : 'dark-chip rounded-full px-3 py-1 text-xs text-yellow-300';
    }
    const container = document.getElementById('dashboard-api-summary');
    if (!container) return;
    const cards = [
        {
            label: 'Balance de hoy',
            value: money(result.today.finance.balance),
            hint: `${result.today.tasks.open_due_count} pendiente(s)`,
        },
        {
            label: 'Balance semanal',
            value: money(result.week.finance.balance),
            hint: `${result.week.finance.transaction_count} movimiento(s)`,
        },
        {
            label: 'Balance mensual',
            value: money(result.month.finance.balance),
            hint: `${money(result.month.finance.income)} / ${money(result.month.finance.expense)}`,
        },
    ];
    container.innerHTML = cards.map((card) => `
        <div class="dark-soft rounded-lg px-4 py-3">
            <p class="text-[11px] text-slate-500">${card.label}</p>
            <p class="font-bold text-slate-100 mt-1">${card.value}</p>
            <p class="text-[11px] text-slate-500 mt-1">${card.hint}</p>
        </div>
    `).join('');
}

export const dashboardBridge = {
    buildLocalSummary,
    load: loadDashboardSummaries,
    render: renderDashboardSummaryBridge,
};
