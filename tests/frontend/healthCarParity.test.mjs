import assert from 'node:assert/strict';
import test from 'node:test';

const {
    buildCarParityReport,
    buildHealthParityReport,
} = await import('../../frontend/assets/js/domains/healthCarParity.js');

function localState() {
    return {
        routine: [{ id: 1, day: 1, time: '06:00', text: 'Gym' }],
        routinePrintNotes: { gym: 'Técnica' },
        fitness: {
            gym: [{ id: 2, week: '2026-W26', exercise: 'Sentadilla' }],
            cardio: [{ id: 3, date: '2026-06-21', minutes: 30 }],
        },
        skincare: {
            morning: [{ id: 1, text: 'Protector' }],
            night: [],
            completions: { '2026-06-22': { morning: [1], night: [] } },
        },
        health: {
            calories: { current: 1800, target: 2200 },
            water: { current: 6, target: 8 },
            activity: { done: true },
            macros: {},
            meals: [{ id: 4, type: 'Comida', desc: 'Demo' }],
            bodyRecords: [{ id: 5, date: '2026-06-20', weight: 82.5 }],
        },
        wellbeing: {
            logs: [{ id: 6, date: '2026-06-21', sleepHours: 7 }],
        },
        vehicle: {
            profile: {
                currentKm: 51000,
                lastServiceKm: 50000,
                lastServiceDate: '2026-06-01',
            },
            kmLogs: [{ id: 7, date: '2026-06-21', km: 51000 }],
            services: [{ id: 8, date: '2026-06-01', km: 50000 }],
            maintenanceLogs: [],
            obligations: {
                refrendo: {},
                seguro: {},
                verificacion: {},
            },
        },
    };
}

test('health parity accepts equivalent API and local health/routine state', () => {
    const state = localState();
    const report = buildHealthParityReport({
        localState: state,
        apiLogs: [
            { logType: 'body', date: '2026-06-20', weight: 82.5, value: 82.5 },
            { logType: 'wellbeing', date: '2026-06-21', sleepHours: 7 },
            { logType: 'meal', date: '2026-06-22' },
            { logType: 'daily_health', date: '2026-06-22', water: { current: 6 } },
        ],
        apiRoutines: [
            { routineType: 'schedule' },
            { routineType: 'gym' },
            { routineType: 'cardio' },
            {
                routineType: 'skincare',
                completions: { '2026-06-22': { morning: [1], night: [] } },
            },
            { routineType: 'health_habits' },
        ],
    });
    assert.equal(report.isMatch, true);
    assert.deepEqual(report.differences, []);
});

test('health parity reports aggregate differences without personal payloads', () => {
    const report = buildHealthParityReport({
        localState: localState(),
        apiLogs: [],
        apiRoutines: [],
    });
    assert.equal(report.isMatch, false);
    assert.ok(report.differences.some((item) => item.metric === 'latestWeight'));
    assert.equal(JSON.stringify(report).includes('Sentadilla'), false);
});

test('car parity accepts equivalent logs, reminders and profile', () => {
    const state = localState();
    const report = buildCarParityReport({
        localState: state,
        apiLogs: [
            { logType: 'odometer', date: '2026-06-21', km: 51000 },
            { logType: 'service', date: '2026-06-01', km: 50000 },
        ],
        apiReminders: [{ reminderType: 'refrendo' }, { reminderType: 'seguro' }, {
            reminderType: 'verificacion',
        }],
        apiSummary: {
            current_odometer_km: 51000,
            profile: state.vehicle.profile,
        },
    });
    assert.equal(report.isMatch, true);
    assert.deepEqual(report.differences, []);
});
