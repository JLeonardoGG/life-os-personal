from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from lifeos.config import Settings
from lifeos.models import (
    AcademicCourse,
    AppSetting,
    Budget,
    CarLog,
    CarReminder,
    Debt,
    DebtMovement,
    Event,
    HealthLog,
    ImportBatch,
    Investment,
    Note,
    Project,
    Routine,
    Subscription,
    Task,
    TaxDocument,
    TaxEntry,
    Transaction,
)
from lifeos.serializers import to_cents
from lifeos.services.files import store_uploaded_bytes

MEXICO_CITY = ZoneInfo("America/Mexico_City")
IMPORTER_VERSION = "v4-health-car"


def canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _state(payload: dict[str, Any]) -> dict[str, Any]:
    state = payload.get("state", payload)
    return state if isinstance(state, dict) else {}


def _date(value: Any, fallback: date | None = None) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return fallback or datetime.now(MEXICO_CITY).date()


def _datetime(value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed = fallback or datetime.now(UTC)
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=MEXICO_CITY)
    return parsed.astimezone(UTC)


def _legacy_key(domain: str, item: Any, index: int = 0) -> str:
    if isinstance(item, dict):
        identifier = item.get("id") or item.get("uuid") or item.get("externalId")
        if identifier is not None:
            return f"legacy:{domain}:{identifier}"
    digest = canonical_hash({"domain": domain, "index": index, "item": item})[:24]
    return f"legacy:{domain}:{digest}"


def _exists(db: Session, model, legacy_key: str) -> bool:
    return db.scalar(select(model.id).where(model.legacy_key == legacy_key)) is not None


def _versioned_payload_hash(payload: dict[str, Any]) -> str:
    return canonical_hash({"importer_version": IMPORTER_VERSION, "payload": payload})


def _duplicate_count(items: list[Any]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for item in items:
        if isinstance(item, dict) and (
            item.get("id") or item.get("uuid") or item.get("externalId")
        ):
            key = str(item.get("id") or item.get("uuid") or item.get("externalId"))
        else:
            key = canonical_hash({"item": item})
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def _has_daily_health(health: dict[str, Any]) -> bool:
    return any(
        key in health
        for key in ("calories", "water", "activity", "macros", "goals")
    )


def preview_legacy_import(payload: dict[str, Any]) -> dict[str, Any]:
    state = _state(payload)
    finance = state.get("finance") or {}
    tax = state.get("uberTax") or {}
    academic = state.get("academic") or {}
    vehicle = state.get("vehicle") or {}
    fitness = state.get("fitness") or {}
    health = state.get("health") or {}
    wellbeing_logs = (state.get("wellbeing") or {}).get("logs") or []
    meals = health.get("meals") or []
    routine_notes = state.get("routinePrintNotes") or {}
    vitamins = state.get("vitamins") or {}
    routine_count = (
        len(state.get("routine") or [])
        + len(fitness.get("gym") or [])
        + len(fitness.get("cardio") or [])
        + (1 if state.get("skincare") else 0)
        + (1 if routine_notes or vitamins else 0)
    )
    health_count = (
        len(health.get("bodyRecords") or [])
        + len(wellbeing_logs)
        + len(meals)
        + (1 if _has_daily_health(health) else 0)
    )
    car_collections = [
        vehicle.get("kmLogs") or [],
        vehicle.get("services") or [],
        vehicle.get("maintenanceLogs") or [],
    ]
    inferred_meal_dates = sum(1 for item in meals if not item.get("date"))
    return {
        "payload_hash": _versioned_payload_hash(payload),
        "source_payload_hash": canonical_hash(payload),
        "importer_version": IMPORTER_VERSION,
        "mode": "preview",
        "counts": {
            "transactions": len(state.get("movements") or []),
            "budgets": len(finance.get("budgets") or {}),
            "subscriptions": len(finance.get("subscriptions") or []),
            "investments": len(state.get("investments") or []),
            "debts": len((state.get("debtLedger") or {}).get("entities") or []),
            "tasks": len(state.get("todos") or []),
            "events": len((state.get("calendar") or {}).get("events") or []),
            "routines": routine_count,
            "health_logs": health_count,
            "academic_courses": len(academic.get("courses") or []),
            "projects": len(academic.get("projects") or []),
            "car_logs": len(vehicle.get("kmLogs") or [])
            + len(vehicle.get("services") or [])
            + len(vehicle.get("maintenanceLogs") or []),
            "car_reminders": len(vehicle.get("obligations") or {}),
            "vehicle_profiles": 1 if vehicle.get("profile") else 0,
            "tax_documents": len(tax.get("cfdi") or []) + len(tax.get("retentions") or []),
            "tax_entries": len(tax.get("incomes") or [])
            + len(tax.get("expenses") or [])
            + len(tax.get("invoices") or []),
            "journal_entries": len(state.get("journal") or {}),
            "photos": len(payload.get("photos") or []),
        },
        "excluded": {
            "credentials": len((state.get("credentials") or {}).get("entries") or []),
        },
        "field_report": {
            "health": {
                "body_records": len(health.get("bodyRecords") or []),
                "wellbeing_logs": len(wellbeing_logs),
                "meals": len(meals),
                "daily_snapshot": 1 if _has_daily_health(health) else 0,
                "meal_dates_inferred": inferred_meal_dates,
            },
            "routines": {
                "schedule": len(state.get("routine") or []),
                "gym": len(fitness.get("gym") or []),
                "cardio": len(fitness.get("cardio") or []),
                "skincare": 1 if state.get("skincare") else 0,
                "health_habits": 1 if routine_notes or vitamins else 0,
            },
            "car": {
                "logs": sum(len(items) for items in car_collections),
                "reminders": len(vehicle.get("obligations") or {}),
                "profile": 1 if vehicle.get("profile") else 0,
            },
            "duplicate_candidates": {
                "health": _duplicate_count(
                    (health.get("bodyRecords") or []) + wellbeing_logs + meals
                ),
                "routines": _duplicate_count(
                    (state.get("routine") or [])
                    + (fitness.get("gym") or [])
                    + (fitness.get("cardio") or [])
                ),
                "car": sum(_duplicate_count(items) for items in car_collections),
            },
            "unmapped": [],
        },
        "warnings": [
            "Las credenciales y contrasenas no se migran.",
            "localStorage e IndexedDB no se modifican durante la importacion.",
            (
                f"{inferred_meal_dates} comida(s) sin fecha usaran la fecha del respaldo."
                if inferred_meal_dates
                else "No fue necesario inferir fechas de comidas."
            ),
        ],
    }


def commit_legacy_import(
    db: Session,
    settings: Settings,
    payload: dict[str, Any],
) -> dict[str, Any]:
    preview = preview_legacy_import(payload)
    payload_hash = preview["payload_hash"]
    previous = db.scalar(
        select(ImportBatch).where(
            ImportBatch.payload_hash == payload_hash,
            ImportBatch.status == "committed",
        )
    )
    if previous:
        return {
            **preview,
            "mode": "commit",
            "status": "already_imported",
            "batch_id": previous.id,
            "inserted": {},
            "existing": previous.counts,
        }

    state = _state(payload)
    snapshot_date = _date(payload.get("exportedAt") or payload.get("exported_at"))
    sanitized_state = json.loads(json.dumps(state))
    sanitized_state.pop("credentials", None)
    counters: dict[str, dict[str, int]] = defaultdict(lambda: {"inserted": 0, "existing": 0})

    def add(model, record, domain: str, item: Any, index: int = 0) -> None:
        key = _legacy_key(domain, item, index)
        if _exists(db, model, key):
            counters[model.__tablename__]["existing"] += 1
            return
        record.legacy_key = key
        db.add(record)
        counters[model.__tablename__]["inserted"] += 1

    for index, item in enumerate(state.get("movements") or []):
        add(
            Transaction,
            Transaction(
                date=_date(item.get("date")),
                type=item.get("type") or "gasto",
                category=item.get("category") or "Otro",
                name=item.get("name") or item.get("desc") or "Movimiento",
                description=item.get("desc") or "",
                amount_cents=to_cents(item.get("amount")),
                expense_nature=item.get("expenseNature") or "",
                source=item.get("source") or "legacy",
                source_hash=item.get("sourceHash"),
                details={key: value for key, value in item.items() if key not in {"password"}},
            ),
            "transactions",
            item,
            index,
        )

    finance = state.get("finance") or {}
    for period, item in (finance.get("budgets") or {}).items():
        limits = {key: to_cents(value) for key, value in (item.get("categoryLimits") or {}).items()}
        add(
            Budget,
            Budget(
                period=period,
                income_target_cents=to_cents(item.get("incomeTarget")),
                expense_limit_cents=to_cents(item.get("expenseLimit")),
                savings_target_cents=to_cents(item.get("savingsTarget")),
                category_limits=limits,
            ),
            "budgets",
            {"id": period},
        )
    for index, item in enumerate(finance.get("subscriptions") or []):
        add(
            Subscription,
            Subscription(
                name=item.get("name") or "Suscripcion",
                amount_cents=to_cents(item.get("amount")),
                category=item.get("category") or "Suscripciones",
                billing_day=int(item.get("day") or 1),
                frequency=item.get("frequency") or "monthly",
                billing_month=item.get("month"),
                payment_method=item.get("paymentMethod") or "",
                active=item.get("active", True),
                notes=item.get("notes") or "",
            ),
            "subscriptions",
            item,
            index,
        )
    for index, item in enumerate(state.get("investments") or []):
        add(
            Investment,
            Investment(
                investment_type=item.get("type") or "Otro",
                institution=item.get("place") or "Sin institucion",
                amount_cents=to_cents(item.get("amount")),
                details=item,
            ),
            "investments",
            item,
            index,
        )

    debt_ledger = state.get("debtLedger") or {}
    transactions_by_entity: dict[str, list[dict]] = defaultdict(list)
    for item in debt_ledger.get("transactions") or []:
        transactions_by_entity[str(item.get("entityId"))].append(item)
    sign = {
        "new_debt": -1,
        "debt_payment": 1,
        "receivable": 1,
        "receivable_payment": -1,
        "adjustment_positive": 1,
        "adjustment_negative": -1,
    }
    for index, entity in enumerate(debt_ledger.get("entities") or []):
        entity_id = str(entity.get("id"))
        entries = transactions_by_entity.get(entity_id, [])
        balance = sum(to_cents(item.get("amount")) * sign.get(item.get("type"), -1) for item in entries)
        debt_key = _legacy_key("debts", entity, index)
        debt = db.scalar(select(Debt).where(Debt.legacy_key == debt_key))
        if not debt:
            debt = Debt(
                legacy_key=debt_key,
                entity=entity.get("name") or "Entidad",
                direction="receivable" if balance > 0 else "owed",
                initial_amount_cents=abs(balance),
                current_amount_cents=abs(balance),
                archived=bool(entity.get("archived")),
                notes=entity.get("notes") or "",
            )
            db.add(debt)
            db.flush()
            counters["debts"]["inserted"] += 1
        else:
            counters["debts"]["existing"] += 1
        for movement_index, item in enumerate(entries):
            add(
                DebtMovement,
                DebtMovement(
                    debt_id=debt.id,
                    date=_date(item.get("date")),
                    kind=item.get("type") or "new_debt",
                    amount_cents=to_cents(item.get("amount")),
                    description=item.get("desc") or "",
                    due_date=_date(item.get("dueDate")) if item.get("dueDate") else None,
                ),
                f"debt-movements:{entity_id}",
                item,
                movement_index,
            )

    for index, item in enumerate(state.get("todos") or []):
        due_at = None
        if item.get("dueDate"):
            due_at = datetime.combine(_date(item["dueDate"]), datetime.min.time(), tzinfo=MEXICO_CITY)
        add(
            Task,
            Task(
                title=item.get("text") or "Pendiente",
                priority=item.get("priority") or "normal",
                due_at=due_at,
                status="done" if item.get("done") else "pending",
                source="legacy",
                details=item,
            ),
            "tasks",
            item,
            index,
        )

    for index, item in enumerate((state.get("calendar") or {}).get("events") or []):
        event_date = _date(item.get("date"))
        start_time = item.get("startTime") or "09:00"
        starts_at = _datetime(f"{event_date.isoformat()}T{start_time}:00")
        ends_at = _datetime(f"{event_date.isoformat()}T{item['endTime']}:00") if item.get("endTime") else None
        add(
            Event,
            Event(
                title=item.get("title") or "Evento",
                description=item.get("notes") or "",
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=not bool(item.get("startTime")),
                recurrence=item.get("recurrence") or "none",
                location=item.get("location") or "",
                source=item.get("source") or "legacy",
                status="done" if item.get("done") else "active",
                details=item,
            ),
            "events",
            item,
            index,
        )

    routine_groups = [
        ("schedule", state.get("routine") or []),
        ("gym", (state.get("fitness") or {}).get("gym") or []),
        ("cardio", (state.get("fitness") or {}).get("cardio") or []),
    ]
    for routine_type, items in routine_groups:
        for index, item in enumerate(items):
            add(
                Routine,
                Routine(
                    routine_type=routine_type,
                    name=item.get("name") or item.get("text") or routine_type.title(),
                    schedule=item,
                    details=item,
                ),
                f"routines:{routine_type}",
                item,
                index,
            )
    skincare = state.get("skincare") or {}
    if skincare:
        add(
            Routine,
            Routine(
                routine_type="skincare",
                name="Skincare",
                schedule={"morning": skincare.get("morning"), "night": skincare.get("night")},
                details={"completions": skincare.get("completions") or {}},
            ),
            "routines:skincare",
            {"id": "skincare"},
        )
    routine_notes = state.get("routinePrintNotes") or {}
    vitamins = state.get("vitamins") or {}
    if routine_notes or vitamins:
        add(
            Routine,
            Routine(
                routine_type="health_habits",
                name="Hábitos de salud",
                schedule={},
                details={
                    "routinePrintNotes": routine_notes,
                    "vitamins": vitamins,
                },
            ),
            "routines:health-habits",
            {"id": "health-habits"},
        )

    health = state.get("health") or {}
    for index, item in enumerate(health.get("bodyRecords") or []):
        add(
            HealthLog,
            HealthLog(
                log_type="body",
                recorded_at=_datetime(f"{_date(item.get('date')).isoformat()}T12:00:00"),
                value=float(item.get("weight")) if item.get("weight") not in (None, "") else None,
                unit="kg",
                notes=item.get("notes") or "",
                details=item,
            ),
            "health:body",
            item,
            index,
        )
    if _has_daily_health(health):
        daily_details = {
            "date": snapshot_date.isoformat(),
            "calories": health.get("calories") or {},
            "water": health.get("water") or {},
            "activity": health.get("activity") or {},
            "macros": health.get("macros") or {},
            "goals": health.get("goals") or {},
        }
        add(
            HealthLog,
            HealthLog(
                log_type="daily_health",
                recorded_at=_datetime(f"{snapshot_date.isoformat()}T12:00:00"),
                value=float((health.get("water") or {}).get("current") or 0),
                unit="glasses",
                details=daily_details,
            ),
            "health:daily",
            {"id": snapshot_date.isoformat()},
        )
    for index, item in enumerate(health.get("meals") or []):
        meal_date = _date(item.get("date"), snapshot_date)
        details = {
            **item,
            "date": meal_date.isoformat(),
            "inferredDate": not bool(item.get("date")),
        }
        add(
            HealthLog,
            HealthLog(
                log_type="meal",
                recorded_at=_datetime(f"{meal_date.isoformat()}T12:00:00"),
                value=None,
                unit="",
                notes=item.get("desc") or "",
                details=details,
            ),
            "health:meals",
            item,
            index,
        )
    for index, item in enumerate((state.get("wellbeing") or {}).get("logs") or []):
        add(
            HealthLog,
            HealthLog(
                log_type="wellbeing",
                recorded_at=_datetime(f"{_date(item.get('date')).isoformat()}T12:00:00"),
                value=(
                    float(item.get("sleepHours", item.get("sleep")))
                    if item.get("sleepHours", item.get("sleep")) not in (None, "")
                    else None
                ),
                unit="hours",
                notes=item.get("notes") or "",
                details=item,
            ),
            "health:wellbeing",
            item,
            index,
        )

    academic = state.get("academic") or {}
    for index, item in enumerate(academic.get("courses") or []):
        add(
            AcademicCourse,
            AcademicCourse(
                name=item.get("name") or "Materia",
                semester=str(item.get("semester") or ""),
                credits=int(item.get("credits") or 0),
                grade=float(item.get("grade")) if item.get("grade") not in (None, "") else None,
                status=item.get("status") or "planned",
                details=item,
            ),
            "academic:courses",
            item,
            index,
        )
    for index, item in enumerate(academic.get("projects") or []):
        add(
            Project,
            Project(
                name=item.get("name") or item.get("title") or "Proyecto",
                project_type=item.get("type") or "academic",
                status=item.get("status") or "idea",
                description=item.get("description") or item.get("notes") or "",
                target_date=_date(item.get("targetDate")) if item.get("targetDate") else None,
                details=item,
            ),
            "academic:projects",
            item,
            index,
        )
    for journal_date, item in (state.get("journal") or {}).items():
        body = item.get("text") if isinstance(item, dict) else str(item)
        title = item.get("title", "") if isinstance(item, dict) else ""
        add(
            Note,
            Note(
                note_type="journal",
                title=title,
                body=body or "",
                note_date=_date(journal_date),
                details=item if isinstance(item, dict) else {},
            ),
            "journal",
            {"id": journal_date},
        )

    vehicle = state.get("vehicle") or {}
    vehicle_profile = vehicle.get("profile") or {}
    if vehicle_profile:
        profile_setting = db.scalar(
            select(AppSetting).where(AppSetting.key == "vehicle_profile")
        )
        if profile_setting:
            counters["app_settings"]["existing"] += 1
        else:
            db.add(
                AppSetting(
                    key="vehicle_profile",
                    value=vehicle_profile,
                    legacy_key="legacy:vehicle:profile",
                )
            )
            counters["app_settings"]["inserted"] += 1
    for collection, log_type in (
        ("kmLogs", "odometer"),
        ("services", "service"),
        ("maintenanceLogs", "maintenance"),
    ):
        for index, item in enumerate(vehicle.get(collection) or []):
            add(
                CarLog,
                CarLog(
                    log_type=log_type,
                    date=_date(item.get("date")),
                    odometer_km=int(item.get("km") or item.get("odometerKm") or 0) or None,
                    amount_cents=to_cents(item.get("cost")),
                    description=item.get("notes") or item.get("type") or "",
                    details=item,
                ),
                f"car:{collection}",
                item,
                index,
            )
    obligations = vehicle.get("obligations") or {}
    for key, item in obligations.items():
        due_date = None
        status_value = "pending"
        if key == "verificacion":
            months = [int(month) for month in item.get("months") or []]
            pending_dates = []
            for month in months:
                period = f"{snapshot_date.year}-{month:02d}"
                if period not in (item.get("donePeriods") or []):
                    pending_dates.append(date(snapshot_date.year, month, 1))
            due_date = min(pending_dates) if pending_dates else None
            status_value = "done" if months and not pending_dates else "pending"
        else:
            month = int(item.get("month") or 0)
            if 1 <= month <= 12:
                due_date = date(snapshot_date.year, month, 1)
            status_value = (
                "done"
                if str(snapshot_date.year) in (item.get("doneYears") or [])
                else "pending"
            )
        reminder_key = _legacy_key("car:reminders", {"id": key})
        existing_reminder = db.scalar(
            select(CarReminder).where(CarReminder.legacy_key == reminder_key)
        )
        if existing_reminder:
            existing_reminder.due_date = existing_reminder.due_date or due_date
            existing_reminder.status = status_value
            existing_reminder.details = item
            counters["car_reminders"]["existing"] += 1
        else:
            db.add(
                CarReminder(
                    legacy_key=reminder_key,
                    reminder_type=key,
                    title=item.get("label") or key,
                    due_date=due_date,
                    recurrence="yearly",
                    status=status_value,
                    details=item,
                )
            )
            counters["car_reminders"]["inserted"] += 1

    tax = state.get("uberTax") or {}
    for collection, document_kind in (("cfdi", "cfdi"), ("retentions", "retention")):
        for index, item in enumerate(tax.get(collection) or []):
            source_hash = item.get("sourceHash") or canonical_hash(item)
            legacy_key = _legacy_key(f"tax:{collection}", item, index)
            if _exists(db, TaxDocument, legacy_key):
                counters["tax_documents"]["existing"] += 1
                continue
            db.add(
                TaxDocument(
                    legacy_key=legacy_key,
                    document_kind=item.get("kind") or document_kind,
                    period=item.get("period") or str(item.get("date") or "")[:7],
                    document_date=_date(item.get("date")) if item.get("date") else None,
                    uuid=item.get("uuid") or None,
                    issuer_rfc=item.get("issuerRfc") or "",
                    receiver_rfc=item.get("receiverRfc") or "",
                    subtotal_cents=to_cents(item.get("subtotal")),
                    tax_transferred_cents=to_cents(item.get("iva")),
                    tax_withheld_cents=to_cents(item.get("totalRetenido")),
                    total_cents=to_cents(item.get("total") or item.get("totalOperacion")),
                    source_hash=source_hash,
                    summary=item,
                )
            )
            counters["tax_documents"]["inserted"] += 1
    for collection, entry_type in (
        ("incomes", "income"),
        ("expenses", "expense"),
        ("invoices", "invoice"),
    ):
        for index, item in enumerate(tax.get(collection) or []):
            add(
                TaxEntry,
                TaxEntry(
                    entry_type=entry_type,
                    period=item.get("period") or str(item.get("date") or "")[:7],
                    date=_date(item.get("date")) if item.get("date") else None,
                    concept=item.get("concept") or item.get("description") or item.get("platform") or "",
                    subtotal_cents=to_cents(item.get("subtotal") or item.get("gross")),
                    tax_cents=to_cents(item.get("iva")),
                    withholding_isr_cents=to_cents(item.get("isrWithheld")),
                    withholding_iva_cents=to_cents(item.get("ivaWithheld")),
                    total_cents=to_cents(item.get("total") or item.get("net")),
                    details=item,
                ),
                f"tax:{collection}",
                item,
                index,
            )

    for index, photo in enumerate(payload.get("photos") or []):
        data_url = photo.get("dataUrl") or ""
        if not data_url.startswith("data:") or "," not in data_url:
            continue
        header, encoded = data_url.split(",", 1)
        content_type = header.split(";", 1)[0].removeprefix("data:")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError:
            continue
        _, created = store_uploaded_bytes(
            db,
            settings,
            content,
            f"progreso-{photo.get('date') or index}.jpg",
            content_type,
            "progress-photos",
            {"date": photo.get("date"), "caption": photo.get("caption")},
        )
        counters["uploaded_files"]["inserted" if created else "existing"] += 1

    snapshot = db.scalar(select(AppSetting).where(AppSetting.key == "legacy_snapshot_latest"))
    if not snapshot:
        snapshot = AppSetting(key="legacy_snapshot_latest")
        db.add(snapshot)
    snapshot.value = {
        "imported_at": datetime.now(UTC).isoformat(),
        "payload_hash": payload_hash,
        "state": sanitized_state,
        "credentials_excluded": True,
    }
    batch = ImportBatch(
        source="localstorage",
        payload_hash=payload_hash,
        status="committed",
        counts={key: value for key, value in counters.items()},
        errors=[],
        committed_at=datetime.now(UTC),
    )
    db.add(batch)
    db.commit()
    return {
        **preview,
        "mode": "commit",
        "status": "committed",
        "batch_id": batch.id,
        "inserted": {key: value["inserted"] for key, value in counters.items()},
        "existing": {key: value["existing"] for key, value in counters.items()},
    }
