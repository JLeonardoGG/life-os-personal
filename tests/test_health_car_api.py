from __future__ import annotations

from datetime import UTC, date, datetime

from lifeos.models import CarLog, HealthLog


def health_payload(**overrides):
    payload = {
        "log_type": "body",
        "recorded_at": "2026-06-22T08:00:00-06:00",
        "value": 82.5,
        "unit": "kg",
        "notes": "Registro demo",
        "metadata": {"waist": 90},
    }
    payload.update(overrides)
    return payload


def test_health_logs_crud_idempotency_stats_and_soft_delete(client):
    payload = health_payload()
    assert client.post("/api/health/logs", json=payload).status_code == 400

    headers = {"Idempotency-Key": "health-create-1"}
    first = client.post("/api/health/logs", json=payload, headers=headers)
    repeated = client.post(
        "/api/health/logs",
        json=health_payload(value=99),
        headers=headers,
    )
    assert first.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    assert repeated.json()["value"] == 82.5

    record = first.json()
    updated = client.put(
        f"/api/health/logs/{record['id']}",
        json={"value": 81.75, "notes": "Actualizado"},
        headers={"Idempotency-Key": "health-update-1"},
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == 81.75

    stats = client.get("/api/health/stats?log_type=body").json()
    assert stats["count"] == 1
    assert stats["average"] == 81.75
    assert stats["by_type"]["body"]["count"] == 1

    assert client.delete(
        f"/api/health/logs/{record['id']}",
        headers={"Idempotency-Key": "health-delete-1"},
    ).status_code == 204
    assert client.delete(f"/api/health/logs/{record['id']}").status_code == 204
    assert client.get("/api/health/logs").json()["total"] == 0


def test_health_validation_and_pagination(client):
    assert client.post(
        "/api/health/logs",
        json=health_payload(value=0),
        headers={"Idempotency-Key": "health-invalid-weight"},
    ).status_code == 422
    assert client.post(
        "/api/health/logs",
        json=health_payload(log_type="wellbeing", value=60, unit="hours"),
        headers={"Idempotency-Key": "health-invalid-sleep"},
    ).status_code == 422
    assert client.post(
        "/api/health/logs",
        json=health_payload(log_type="water", value=-1, unit="glasses"),
        headers={"Idempotency-Key": "health-invalid-water"},
    ).status_code == 422

    database = client.app.state.database
    with database.session() as db:
        db.add_all(
            [
                HealthLog(
                    log_type="water",
                    recorded_at=datetime(2026, 6, 22, 12, index % 60, tzinfo=UTC),
                    value=float(index % 9),
                    unit="glasses",
                )
                for index in range(505)
            ]
        )
        db.commit()
    first = client.get("/api/health/logs?log_type=water&limit=200").json()
    last = client.get("/api/health/logs?log_type=water&limit=200&offset=400").json()
    assert first["total"] == 505
    assert len(first["items"]) == 200
    assert len(last["items"]) == 105


def test_routine_crud_idempotency_and_soft_delete(client):
    payload = {
        "routine_type": "gym",
        "name": "Pierna demo",
        "schedule": {"week": "2026-W26", "sets": 4},
        "metadata": {"exercise": "Sentadilla"},
    }
    headers = {"Idempotency-Key": "routine-create-1"}
    first = client.post("/api/routines", json=payload, headers=headers)
    repeated = client.post(
        "/api/routines",
        json={**payload, "name": "No debe duplicarse"},
        headers=headers,
    )
    assert first.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    assert client.get("/api/routines?routine_type=gym").json()["total"] == 1

    updated = client.put(
        f"/api/routines/{first.json()['id']}",
        json={"name": "Pierna actualizada", "active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["active"] is False
    assert client.delete(f"/api/routines/{first.json()['id']}").status_code == 204
    assert client.get("/api/routines").json()["total"] == 0


def test_car_crud_summary_idempotency_validation_and_soft_delete(client):
    profile = client.put(
        "/api/car/profile",
        json={
            "name": "Auto demo",
            "currentKm": 51000,
            "serviceIntervalKm": 10000,
            "serviceIntervalMonths": 6,
        },
    )
    assert profile.status_code == 200

    log_payload = {
        "log_type": "service",
        "date": "2026-06-01",
        "odometer_km": 50000,
        "amount": 2500.5,
        "description": "Servicio demo",
        "metadata": {"shop": "Taller demo"},
    }
    headers = {"Idempotency-Key": "car-log-create-1"}
    first = client.post("/api/car/logs", json=log_payload, headers=headers)
    repeated = client.post(
        "/api/car/logs",
        json={**log_payload, "amount": 9999},
        headers=headers,
    )
    assert first.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    assert repeated.json()["amount"] == 2500.5

    invalid = client.post(
        "/api/car/logs",
        json={**log_payload, "odometer_km": -1},
        headers={"Idempotency-Key": "car-log-invalid"},
    )
    assert invalid.status_code == 422

    updated = client.put(
        f"/api/car/logs/{first.json()['id']}",
        json={"amount": 2600.25, "description": "Servicio actualizado"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 2600.25

    reminder = client.post(
        "/api/car/reminders",
        json={
            "reminder_type": "seguro",
            "title": "Renovar seguro demo",
            "due_date": "2027-03-01",
            "recurrence": "yearly",
        },
        headers={"Idempotency-Key": "car-reminder-create-1"},
    )
    assert reminder.status_code == 201
    reminder_id = reminder.json()["id"]
    assert client.put(
        f"/api/car/reminders/{reminder_id}",
        json={"status": "done"},
    ).json()["status"] == "done"

    summary = client.get("/api/car/summary").json()
    assert summary["current_odometer_km"] == 51000
    assert summary["latest_service"]["id"] == first.json()["id"]
    assert summary["next_service"]["due_odometer_km"] == 60000
    assert summary["next_service"]["due_date"] == "2026-12-01"
    assert summary["profile"]["name"] == "Auto demo"

    assert client.delete(f"/api/car/logs/{first.json()['id']}").status_code == 204
    assert client.delete(f"/api/car/reminders/{reminder_id}").status_code == 204
    assert client.get("/api/car/logs").json()["total"] == 0
    assert client.get("/api/car/reminders").json()["total"] == 0


def test_health_car_legacy_migration_preview_commit_and_parity(client):
    payload = {
        "app": "LifeOS",
        "exportedAt": "2026-06-22T09:00:00-06:00",
        "state": {
            "routine": [
                {
                    "id": "schedule-1",
                    "day": 1,
                    "time": "06:00",
                    "text": "Gym",
                    "color": "bg-red-500",
                }
            ],
            "routinePrintNotes": {"gym": "Técnica antes que peso"},
            "fitness": {
                "gym": [
                    {
                        "id": "gym-1",
                        "week": "2026-W26",
                        "exercise": "Sentadilla",
                        "weight": 80,
                    }
                ],
                "cardio": [
                    {
                        "id": "cardio-1",
                        "date": "2026-06-21",
                        "minutes": 30,
                        "type": "Caminata",
                    }
                ],
            },
            "skincare": {
                "morning": [{"id": 1, "text": "Protector"}],
                "night": [],
                "completions": {"2026-06-22": {"morning": [1], "night": []}},
            },
            "health": {
                "calories": {"current": 1800, "target": 2200},
                "water": {"current": 6, "target": 8},
                "activity": {"done": True, "type": "Gym"},
                "macros": {"p": {"c": 120, "t": 150}},
                "goals": {"targetWeight": 75, "targetDate": "2026-12-31"},
                "meals": [{"id": "meal-1", "type": "Comida", "desc": "Arroz y pollo"}],
                "bodyRecords": [
                    {"id": "body-1", "date": "2026-06-20", "weight": 82.5, "waist": 90}
                ],
            },
            "wellbeing": {
                "logs": [
                    {
                        "id": "wellbeing-1",
                        "date": "2026-06-21",
                        "sleep": 7,
                        "mood": 4,
                    }
                ]
            },
            "vehicle": {
                "profile": {
                    "name": "Auto demo",
                    "currentKm": 51000,
                    "serviceIntervalKm": 10000,
                    "serviceIntervalMonths": 6,
                },
                "kmLogs": [{"id": "km-1", "date": "2026-06-21", "km": 51000}],
                "services": [
                    {
                        "id": "service-1",
                        "date": "2026-06-01",
                        "km": 50000,
                        "cost": 2500,
                    }
                ],
                "maintenanceLogs": [],
                "obligations": {
                    "refrendo": {
                        "label": "Refrendo",
                        "month": 1,
                        "doneYears": ["2026"],
                    },
                    "seguro": {
                        "label": "Seguro",
                        "month": 3,
                        "doneYears": [],
                    },
                    "verificacion": {
                        "label": "Verificación",
                        "months": [1, 7],
                        "donePeriods": ["2026-01"],
                    },
                },
            },
        },
        "photos": [],
    }
    preview = client.post("/api/import/localstorage?mode=preview", json=payload)
    assert preview.status_code == 200
    report = preview.json()
    assert report["importer_version"] == "v4-health-car"
    assert report["counts"]["health_logs"] == 4
    assert report["counts"]["routines"] == 5
    assert report["counts"]["car_logs"] == 2
    assert report["counts"]["car_reminders"] == 3
    assert report["field_report"]["health"]["meal_dates_inferred"] == 1

    first = client.post("/api/import/localstorage?mode=commit", json=payload)
    second = client.post("/api/import/localstorage?mode=commit", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "committed"
    assert second.json()["status"] == "already_imported"

    health = client.get("/api/health/logs?limit=50").json()
    routines = client.get("/api/routines?limit=50").json()
    car_logs = client.get("/api/car/logs?limit=50").json()
    reminders = client.get("/api/car/reminders?limit=50").json()
    summary = client.get("/api/car/summary").json()
    assert health["total"] == 4
    assert {item["log_type"] for item in health["items"]} == {
        "body",
        "wellbeing",
        "daily_health",
        "meal",
    }
    assert routines["total"] == 5
    assert car_logs["total"] == 2
    assert reminders["total"] == 3
    assert summary["profile"]["currentKm"] == 51000
    assert summary["current_odometer_km"] == 51000


def test_car_pagination(client):
    database = client.app.state.database
    with database.session() as db:
        db.add_all(
            [
                CarLog(
                    log_type="odometer",
                    date=date(2026, 6, 22),
                    odometer_km=50000 + index,
                )
                for index in range(505)
            ]
        )
        db.commit()
    first = client.get("/api/car/logs?log_type=odometer&limit=200").json()
    last = client.get("/api/car/logs?log_type=odometer&limit=200&offset=400").json()
    assert first["total"] == 505
    assert len(first["items"]) == 200
    assert len(last["items"]) == 105
