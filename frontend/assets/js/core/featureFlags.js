export const FEATURE_FLAGS = {
    useApiForSummary: true,
    useApiForTransactions: true,
    useApiForBudgets: true,
    useApiForSubscriptions: true,
    useApiForDebts: true,
    useApiForInvestments: true,
    useApiForTasks: true,
    useApiForEvents: true,
    useApiForHealth: true,
    useApiForRoutines: true,
    useApiForCar: true,
    useApiForTax: false,
    allowLocalStorageFallback: true,
    showBackendStatus: true,
};

const FINANCE_OVERRIDE_KEY = 'lifeos_finance_feature_flags_v1';
const HEALTH_CAR_OVERRIDE_KEY = 'lifeos_health_car_feature_flags_v1';

function readFinanceOverrides() {
    try {
        return JSON.parse(globalThis.localStorage?.getItem(FINANCE_OVERRIDE_KEY) || '{}');
    } catch {
        return {};
    }
}

const financeOverrides = readFinanceOverrides();

export const FINANCE_WRITE_FLAGS = {
    useApiForTransactionWrites: financeOverrides.useApiForTransactionWrites === true,
    useApiForBudgetWrites: financeOverrides.useApiForBudgetWrites === true,
    useApiForSubscriptionWrites: financeOverrides.useApiForSubscriptionWrites === true,
    useApiForDebtWrites: financeOverrides.useApiForDebtWrites === true,
    useApiForInvestmentWrites: financeOverrides.useApiForInvestmentWrites === true,
};

export function setFinanceWriteFlag(flag, enabled) {
    if (!(flag in FINANCE_WRITE_FLAGS)) throw new Error(`Unknown finance write flag: ${flag}`);
    FINANCE_WRITE_FLAGS[flag] = Boolean(enabled);
    globalThis.localStorage?.setItem(
        FINANCE_OVERRIDE_KEY,
        JSON.stringify(FINANCE_WRITE_FLAGS),
    );
    return { ...FINANCE_WRITE_FLAGS };
}

function readHealthCarOverrides() {
    try {
        return JSON.parse(globalThis.localStorage?.getItem(HEALTH_CAR_OVERRIDE_KEY) || '{}');
    } catch {
        return {};
    }
}

const healthCarOverrides = readHealthCarOverrides();

export const HEALTH_CAR_WRITE_FLAGS = {
    useApiForHealthWrites: healthCarOverrides.useApiForHealthWrites === true,
    useApiForRoutineWrites: healthCarOverrides.useApiForRoutineWrites === true,
    useApiForCarWrites: healthCarOverrides.useApiForCarWrites === true,
};

export function setHealthCarWriteFlag(flag, enabled) {
    if (!(flag in HEALTH_CAR_WRITE_FLAGS)) {
        throw new Error(`Unknown health/car write flag: ${flag}`);
    }
    HEALTH_CAR_WRITE_FLAGS[flag] = Boolean(enabled);
    globalThis.localStorage?.setItem(
        HEALTH_CAR_OVERRIDE_KEY,
        JSON.stringify(HEALTH_CAR_WRITE_FLAGS),
    );
    return { ...HEALTH_CAR_WRITE_FLAGS };
}
