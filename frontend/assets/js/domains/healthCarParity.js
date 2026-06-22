function countBy(items, key) {
    return (items || []).reduce((result, item) => {
        const value = item[key] || 'unknown';
        result[value] = (result[value] || 0) + 1;
        return result;
    }, {});
}

function latestByDate(items) {
    return [...(items || [])].sort((left, right) => (
        String(left.date || left.recordedAt || '').localeCompare(
            String(right.date || right.recordedAt || ''),
        )
    )).at(-1) || null;
}

function completionCount(completions) {
    return Object.values(completions || {}).reduce((total, day) => (
        total + (day?.morning?.length || 0) + (day?.night?.length || 0)
    ), 0);
}

function compare(section, metric, api, local, differences) {
    if (JSON.stringify(api) !== JSON.stringify(local)) {
        differences.push({ section, metric, api, local });
    }
}

export function buildHealthParityReport({ apiLogs = [], apiRoutines = [], localState = {} } = {}) {
    const health = localState.health || {};
    const wellbeing = localState.wellbeing || {};
    const fitness = localState.fitness || {};
    const skincare = localState.skincare || {};
    const latestBody = latestByDate(apiLogs.filter((item) => item.logType === 'body'));
    const dailyHealth = latestByDate(apiLogs.filter((item) => item.logType === 'daily_health'));
    const skincareRoutine = apiRoutines.find((item) => item.routineType === 'skincare');
    const api = {
        logCounts: countBy(apiLogs, 'logType'),
        latestWeight: latestBody ? Number(latestBody.weight || latestBody.value || 0) : null,
        waterCurrent: dailyHealth
            ? Number(dailyHealth.water?.current ?? dailyHealth.value ?? 0)
            : null,
        wellbeing: apiLogs.filter((item) => item.logType === 'wellbeing').length,
        routines: countBy(apiRoutines, 'routineType'),
        skincareCompletions: completionCount(skincareRoutine?.completions),
    };
    const local = {
        logCounts: {
            body: (health.bodyRecords || []).length,
            wellbeing: (wellbeing.logs || []).length,
            meal: (health.meals || []).length,
            daily_health: health.calories || health.water || health.activity || health.macros ? 1 : 0,
        },
        latestWeight: latestByDate(health.bodyRecords)?.weight ?? null,
        waterCurrent: health.water ? Number(health.water.current || 0) : null,
        wellbeing: (wellbeing.logs || []).length,
        routines: {
            schedule: (localState.routine || []).length,
            gym: (fitness.gym || []).length,
            cardio: (fitness.cardio || []).length,
            skincare: localState.skincare ? 1 : 0,
            health_habits: localState.routinePrintNotes ? 1 : 0,
        },
        skincareCompletions: completionCount(skincare.completions),
    };
    const differences = [];
    Object.keys(local.logCounts).forEach((type) => {
        compare('health', `logs.${type}`, api.logCounts[type] || 0, local.logCounts[type], differences);
    });
    Object.keys(local.routines).forEach((type) => {
        compare(
            'routines',
            `count.${type}`,
            api.routines[type] || 0,
            local.routines[type],
            differences,
        );
    });
    compare('health', 'latestWeight', api.latestWeight, local.latestWeight, differences);
    compare('health', 'waterCurrent', api.waterCurrent, local.waterCurrent, differences);
    compare(
        'routines',
        'skincareCompletions',
        api.skincareCompletions,
        local.skincareCompletions,
        differences,
    );
    return {
        domain: 'health',
        isMatch: differences.length === 0,
        checkedAt: new Date().toISOString(),
        api,
        local,
        differences,
    };
}

function localReminderCount(obligations) {
    return Object.keys(obligations || {}).length;
}

export function buildCarParityReport({
    apiLogs = [],
    apiReminders = [],
    apiSummary = {},
    localState = {},
} = {}) {
    const vehicle = localState.vehicle || {};
    const allLocalLogs = [
        ...(vehicle.kmLogs || []).map((item) => ({ ...item, logType: 'odometer' })),
        ...(vehicle.services || []).map((item) => ({ ...item, logType: 'service' })),
        ...(vehicle.maintenanceLogs || []).map((item) => ({ ...item, logType: 'maintenance' })),
    ];
    const latestLocal = latestByDate(vehicle.kmLogs || []);
    const api = {
        logCounts: countBy(apiLogs, 'logType'),
        latestKm: Number(apiSummary.current_odometer_km || 0),
        reminders: apiReminders.length,
        profile: {
            currentKm: Number(apiSummary.profile?.currentKm || 0),
            lastServiceKm: Number(apiSummary.profile?.lastServiceKm || 0),
            lastServiceDate: apiSummary.profile?.lastServiceDate || '',
        },
    };
    const local = {
        logCounts: countBy(allLocalLogs, 'logType'),
        latestKm: Math.max(
            Number(latestLocal?.km || 0),
            Number(vehicle.profile?.currentKm || 0),
        ),
        reminders: localReminderCount(vehicle.obligations),
        profile: {
            currentKm: Number(vehicle.profile?.currentKm || 0),
            lastServiceKm: Number(vehicle.profile?.lastServiceKm || 0),
            lastServiceDate: vehicle.profile?.lastServiceDate || '',
        },
    };
    const differences = [];
    ['odometer', 'service', 'maintenance'].forEach((type) => {
        compare('car', `logs.${type}`, api.logCounts[type] || 0, local.logCounts[type] || 0, differences);
    });
    compare('car', 'latestKm', api.latestKm, local.latestKm, differences);
    compare('car', 'reminders', api.reminders, local.reminders, differences);
    compare('car', 'profile', api.profile, local.profile, differences);
    return {
        domain: 'car',
        isMatch: differences.length === 0,
        checkedAt: new Date().toISOString(),
        api,
        local,
        differences,
    };
}

export const healthCarParity = {
    buildHealthReport: buildHealthParityReport,
    buildCarReport: buildCarParityReport,
};
