from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from lifeos.database import get_db
from lifeos.models import (
    AppSetting,
    AutomationLog,
    CarLog,
    CarReminder,
    Event,
    HealthLog,
    Note,
    Routine,
    Task,
)
from lifeos.schemas import (
    CarLogCreate,
    CarLogUpdate,
    CarReminderCreate,
    CarReminderUpdate,
    EventCreate,
    EventUpdate,
    HealthLogCreate,
    HealthLogUpdate,
    NoteCreate,
    Page,
    RoutineCreate,
    RoutineUpdate,
    TaskCreate,
    TaskUpdate,
    validate_health_range,
)
from lifeos.security import require_session_or_api_key
from lifeos.serializers import model_dict, to_cents

router = APIRouter(
    prefix="/api",
    tags=["life"],
    dependencies=[Depends(require_session_or_api_key)],
)
MEXICO_CITY = ZoneInfo("America/Mexico_City")


def _active(model):
    return model.deleted_at.is_(None)


def _get_or_404(db: Session, model, record_id: str):
    record = db.scalar(select(model).where(model.id == record_id, _active(model)))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


def _page(db: Session, query, limit: int, offset: int, money_fields=None) -> Page:
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return Page(
        items=[model_dict(item, money_fields) for item in records],
        total=total,
        limit=limit,
        offset=offset,
    )


def _idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not idempotency_key or len(idempotency_key) > 160:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key header is required")
    return idempotency_key


def _optional_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str | None:
    if idempotency_key and len(idempotency_key) > 160:
        raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
    return idempotency_key


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=MEXICO_CITY)
    return value.astimezone(UTC)


def _audit(
    db: Session,
    *,
    action: str,
    endpoint: str,
    entity_id: str,
    entity_type: str,
    idempotency_key: str | None = None,
) -> None:
    db.add(
        AutomationLog(
            source="local_api",
            action=action,
            endpoint=endpoint,
            result="success",
            idempotency_key=idempotency_key,
            entity_id=entity_id,
            details={"entity_type": entity_type},
        )
    )


def _commit(db: Session, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail=detail) from error


def _existing_by_idempotency(db: Session, model, idempotency_key: str):
    existing = db.scalar(select(model).where(model.idempotency_key == idempotency_key))
    if existing and existing.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Idempotency-Key belongs to a deleted record")
    return existing


def _month_add(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


@router.get("/tasks", response_model=Page)
def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Task).where(_active(Task))
    if status_filter:
        query = query.where(Task.status == status_filter)
    return _page(db, query.order_by(Task.due_at.asc(), Task.created_at.desc()), limit, offset)


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> dict:
    record = Task(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
        status=payload.status,
        source=payload.source,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record)


@router.put("/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)) -> dict:
    record = _get_or_404(db, Task, task_id)
    data = payload.model_dump(exclude_unset=True)
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    return model_dict(record)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: Session = Depends(get_db)) -> None:
    record = _get_or_404(db, Task, task_id)
    record.deleted_at = datetime.now(UTC)
    db.commit()


@router.get("/events", response_model=Page)
def list_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Event).where(_active(Event)).order_by(Event.starts_at.asc())
    return _page(db, query, limit, offset)


@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> dict:
    record = Event(
        title=payload.title,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        all_day=payload.all_day,
        recurrence=payload.recurrence,
        location=payload.location,
        source=payload.source,
        status=payload.status,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record)


@router.put("/events/{event_id}")
def update_event(event_id: str, payload: EventUpdate, db: Session = Depends(get_db)) -> dict:
    record = _get_or_404(db, Event, event_id)
    data = payload.model_dump(exclude_unset=True)
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    return model_dict(record)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: str, db: Session = Depends(get_db)) -> None:
    record = _get_or_404(db, Event, event_id)
    record.deleted_at = datetime.now(UTC)
    db.commit()


@router.get("/routines", response_model=Page)
def list_routines(
    routine_type: str | None = None,
    active: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Routine).where(_active(Routine))
    if routine_type:
        query = query.where(Routine.routine_type == routine_type)
    if active is not None:
        query = query.where(Routine.active == active)
    return _page(db, query.order_by(Routine.routine_type, Routine.name), limit, offset)


@router.post("/routines", status_code=status.HTTP_201_CREATED)
def create_routine(
    payload: RoutineCreate,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    existing = _existing_by_idempotency(db, Routine, idempotency_key)
    if existing:
        return model_dict(existing)
    record = Routine(
        routine_type=payload.routine_type,
        name=payload.name,
        schedule=payload.schedule,
        active=payload.active,
        idempotency_key=idempotency_key,
        details=payload.metadata,
    )
    try:
        db.add(record)
        db.flush()
        _audit(
            db,
            action="routine.create",
            endpoint="/api/routines",
            entity_id=record.id,
            entity_type="routine",
            idempotency_key=idempotency_key,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_by_idempotency(db, Routine, idempotency_key)
        if existing:
            return model_dict(existing)
        raise HTTPException(status_code=409, detail="Routine conflicts with an existing record") from None
    return model_dict(record)


@router.put("/routines/{routine_id}")
def update_routine(
    routine_id: str,
    payload: RoutineUpdate,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, Routine, routine_id)
    data = payload.model_dump(exclude_unset=True)
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    _audit(
        db,
        action="routine.update",
        endpoint=f"/api/routines/{routine_id}",
        entity_id=record.id,
        entity_type="routine",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Routine could not be updated")
    return model_dict(record)


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routine(
    routine_id: str,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> None:
    record = db.scalar(select(Routine).where(Routine.id == routine_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is not None:
        return
    record.deleted_at = datetime.now(UTC)
    _audit(
        db,
        action="routine.delete",
        endpoint=f"/api/routines/{routine_id}",
        entity_id=record.id,
        entity_type="routine",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Routine could not be deleted")


@router.get("/health/logs", response_model=Page)
def list_health_logs(
    log_type: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(HealthLog).where(_active(HealthLog))
    if log_type:
        query = query.where(HealthLog.log_type == log_type)
    if start_at:
        query = query.where(HealthLog.recorded_at >= _utc(start_at))
    if end_at:
        query = query.where(HealthLog.recorded_at <= _utc(end_at))
    return _page(db, query.order_by(HealthLog.recorded_at.desc()), limit, offset)


def _create_health_log(
    payload: HealthLogCreate,
    idempotency_key: str,
    db: Session,
) -> dict:
    existing = _existing_by_idempotency(db, HealthLog, idempotency_key)
    if existing:
        return model_dict(existing)
    record = HealthLog(
        log_type=payload.log_type,
        recorded_at=_utc(payload.recorded_at),
        value=payload.value,
        unit=payload.unit,
        notes=payload.notes,
        idempotency_key=idempotency_key,
        details=payload.metadata,
    )
    try:
        db.add(record)
        db.flush()
        _audit(
            db,
            action="health_log.create",
            endpoint="/api/health/logs",
            entity_id=record.id,
            entity_type="health_log",
            idempotency_key=idempotency_key,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_by_idempotency(db, HealthLog, idempotency_key)
        if existing:
            return model_dict(existing)
        raise HTTPException(status_code=409, detail="Health log conflicts with an existing record") from None
    return model_dict(record)


@router.post("/health/logs", status_code=status.HTTP_201_CREATED)
def create_health_log(
    payload: HealthLogCreate,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    return _create_health_log(payload, idempotency_key, db)


@router.post("/health/log", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_health_log_legacy_alias(
    payload: HealthLogCreate,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    return _create_health_log(payload, idempotency_key, db)


@router.put("/health/logs/{log_id}")
def update_health_log(
    log_id: str,
    payload: HealthLogUpdate,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, HealthLog, log_id)
    data = payload.model_dump(exclude_unset=True)
    effective_type = data.get("log_type", record.log_type)
    effective_value = data.get("value", record.value)
    validate_health_range(effective_type, effective_value)
    if "recorded_at" in data:
        data["recorded_at"] = _utc(data["recorded_at"])
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    _audit(
        db,
        action="health_log.update",
        endpoint=f"/api/health/logs/{log_id}",
        entity_id=record.id,
        entity_type="health_log",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Health log could not be updated")
    return model_dict(record)


@router.delete("/health/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_health_log(
    log_id: str,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> None:
    record = db.scalar(select(HealthLog).where(HealthLog.id == log_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is not None:
        return
    record.deleted_at = datetime.now(UTC)
    _audit(
        db,
        action="health_log.delete",
        endpoint=f"/api/health/logs/{log_id}",
        entity_id=record.id,
        entity_type="health_log",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Health log could not be deleted")


@router.get("/health/stats")
def health_stats(
    log_type: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    db: Session = Depends(get_db),
) -> dict:
    query = select(HealthLog).where(_active(HealthLog))
    if log_type:
        query = query.where(HealthLog.log_type == log_type)
    if start_at:
        query = query.where(HealthLog.recorded_at >= _utc(start_at))
    if end_at:
        query = query.where(HealthLog.recorded_at <= _utc(end_at))
    records = db.scalars(query.order_by(HealthLog.recorded_at.desc())).all()
    values = [item.value for item in records if item.value is not None]
    by_type: dict[str, dict] = {}
    for item in records:
        summary = by_type.setdefault(item.log_type, {"count": 0, "values": []})
        summary["count"] += 1
        if item.value is not None:
            summary["values"].append(item.value)
    grouped = {}
    for key, summary in by_type.items():
        grouped[key] = {
            "count": summary["count"],
            "average": (
                sum(summary["values"]) / len(summary["values"])
                if summary["values"]
                else None
            ),
        }
    return {
        "count": len(records),
        "average": sum(values) / len(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "latest": model_dict(records[0]) if records else None,
        "by_type": grouped,
    }


@router.get("/car/logs", response_model=Page)
def list_car_logs(
    log_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(CarLog).where(_active(CarLog))
    if log_type:
        query = query.where(CarLog.log_type == log_type)
    if start_date:
        query = query.where(CarLog.date >= start_date)
    if end_date:
        query = query.where(CarLog.date <= end_date)
    return _page(db, query.order_by(CarLog.date.desc()), limit, offset, {"amount_cents": "amount"})


@router.post("/car/logs", status_code=status.HTTP_201_CREATED)
def create_car_log(
    payload: CarLogCreate,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    existing = _existing_by_idempotency(db, CarLog, idempotency_key)
    if existing:
        return model_dict(existing, {"amount_cents": "amount"})
    record = CarLog(
        log_type=payload.log_type,
        date=payload.date,
        odometer_km=payload.odometer_km,
        amount_cents=to_cents(payload.amount),
        description=payload.description,
        idempotency_key=idempotency_key,
        details=payload.metadata,
    )
    try:
        db.add(record)
        db.flush()
        _audit(
            db,
            action="car_log.create",
            endpoint="/api/car/logs",
            entity_id=record.id,
            entity_type="car_log",
            idempotency_key=idempotency_key,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_by_idempotency(db, CarLog, idempotency_key)
        if existing:
            return model_dict(existing, {"amount_cents": "amount"})
        raise HTTPException(status_code=409, detail="Car log conflicts with an existing record") from None
    return model_dict(record, {"amount_cents": "amount"})


@router.put("/car/logs/{log_id}")
def update_car_log(
    log_id: str,
    payload: CarLogUpdate,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, CarLog, log_id)
    data = payload.model_dump(exclude_unset=True)
    if "amount" in data:
        record.amount_cents = to_cents(data.pop("amount"))
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    _audit(
        db,
        action="car_log.update",
        endpoint=f"/api/car/logs/{log_id}",
        entity_id=record.id,
        entity_type="car_log",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Car log could not be updated")
    return model_dict(record, {"amount_cents": "amount"})


@router.delete("/car/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car_log(
    log_id: str,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> None:
    record = db.scalar(select(CarLog).where(CarLog.id == log_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is not None:
        return
    record.deleted_at = datetime.now(UTC)
    _audit(
        db,
        action="car_log.delete",
        endpoint=f"/api/car/logs/{log_id}",
        entity_id=record.id,
        entity_type="car_log",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Car log could not be deleted")


@router.get("/car/reminders", response_model=Page)
def list_car_reminders(
    reminder_type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(CarReminder).where(_active(CarReminder))
    if reminder_type:
        query = query.where(CarReminder.reminder_type == reminder_type)
    if status_filter:
        query = query.where(CarReminder.status == status_filter)
    return _page(db, query.order_by(CarReminder.due_date.asc()), limit, offset)


@router.post("/car/reminders", status_code=status.HTTP_201_CREATED)
def create_car_reminder(
    payload: CarReminderCreate,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    existing = _existing_by_idempotency(db, CarReminder, idempotency_key)
    if existing:
        return model_dict(existing)
    record = CarReminder(
        reminder_type=payload.reminder_type,
        title=payload.title,
        due_date=payload.due_date,
        due_odometer_km=payload.due_odometer_km,
        recurrence=payload.recurrence,
        status=payload.status,
        idempotency_key=idempotency_key,
        details=payload.metadata,
    )
    try:
        db.add(record)
        db.flush()
        _audit(
            db,
            action="car_reminder.create",
            endpoint="/api/car/reminders",
            entity_id=record.id,
            entity_type="car_reminder",
            idempotency_key=idempotency_key,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_by_idempotency(db, CarReminder, idempotency_key)
        if existing:
            return model_dict(existing)
        raise HTTPException(
            status_code=409,
            detail="Car reminder conflicts with an existing record",
        ) from None
    return model_dict(record)


@router.put("/car/reminders/{reminder_id}")
def update_car_reminder(
    reminder_id: str,
    payload: CarReminderUpdate,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, CarReminder, reminder_id)
    data = payload.model_dump(exclude_unset=True)
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    _audit(
        db,
        action="car_reminder.update",
        endpoint=f"/api/car/reminders/{reminder_id}",
        entity_id=record.id,
        entity_type="car_reminder",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Car reminder could not be updated")
    return model_dict(record)


@router.delete("/car/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car_reminder(
    reminder_id: str,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> None:
    record = db.scalar(select(CarReminder).where(CarReminder.id == reminder_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is not None:
        return
    record.deleted_at = datetime.now(UTC)
    _audit(
        db,
        action="car_reminder.delete",
        endpoint=f"/api/car/reminders/{reminder_id}",
        entity_id=record.id,
        entity_type="car_reminder",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Car reminder could not be deleted")


@router.get("/car/summary")
def car_summary(db: Session = Depends(get_db)) -> dict:
    logs = db.scalars(
        select(CarLog).where(_active(CarLog)).order_by(CarLog.date.desc())
    ).all()
    reminders = db.scalars(
        select(CarReminder)
        .where(_active(CarReminder), CarReminder.status != "done")
        .order_by(CarReminder.due_date.asc())
    ).all()
    profile_setting = db.scalar(select(AppSetting).where(AppSetting.key == "vehicle_profile"))
    profile = profile_setting.value if profile_setting else {}
    current_odometer = max(
        [int(item.odometer_km or 0) for item in logs]
        + [int(profile.get("currentKm") or 0)],
        default=0,
    )
    services = [item for item in logs if item.log_type == "service"]
    latest_service = services[0] if services else None
    if latest_service:
        service_km = int(latest_service.odometer_km or 0)
        service_date = latest_service.date
    else:
        service_km = int(profile.get("lastServiceKm") or 0)
        try:
            service_date = (
                date.fromisoformat(profile["lastServiceDate"])
                if profile.get("lastServiceDate")
                else None
            )
        except ValueError:
            service_date = None
    interval_km = max(1, int(profile.get("serviceIntervalKm") or 10000))
    interval_months = max(1, int(profile.get("serviceIntervalMonths") or 6))
    next_service = {
        "due_odometer_km": service_km + interval_km if service_km else None,
        "due_date": _month_add(service_date, interval_months).isoformat() if service_date else None,
        "km_since_service": max(0, current_odometer - service_km) if service_km else None,
    }
    return {
        "log_count": len(logs),
        "reminder_count": len(reminders),
        "current_odometer_km": current_odometer,
        "latest_service": (
            model_dict(latest_service, {"amount_cents": "amount"})
            if latest_service
            else None
        ),
        "next_service": next_service,
        "upcoming_reminders": [model_dict(item) for item in reminders[:10]],
        "profile": profile,
    }


@router.put("/car/profile")
def update_car_profile(
    payload: dict,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    forbidden = {"password", "pin", "token", "cvv", "nip"}
    if any(key.lower() in forbidden for key in payload):
        raise HTTPException(status_code=422, detail="Sensitive credentials are not allowed")
    nonnegative = (
        "currentKm",
        "lastServiceKm",
        "serviceIntervalKm",
        "warningKm",
        "serviceIntervalMonths",
        "warningMonths",
        "targetKm",
    )
    for key in nonnegative:
        if key in payload and float(payload[key] or 0) < 0:
            raise HTTPException(status_code=422, detail=f"{key} cannot be negative")
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "vehicle_profile"))
    if not setting:
        setting = AppSetting(key="vehicle_profile", value={})
        db.add(setting)
        db.flush()
    setting.value = {**(setting.value or {}), **payload}
    _audit(
        db,
        action="car_profile.update",
        endpoint="/api/car/profile",
        entity_id=setting.id,
        entity_type="app_setting",
        idempotency_key=idempotency_key,
    )
    _commit(db, "Vehicle profile could not be updated")
    return setting.value


@router.get("/notes", response_model=Page)
def list_notes(
    note_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Note).where(_active(Note))
    if note_type:
        query = query.where(Note.note_type == note_type)
    return _page(db, query.order_by(Note.note_date.desc(), Note.created_at.desc()), limit, offset)


@router.post("/notes", status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate, db: Session = Depends(get_db)) -> dict:
    record = Note(
        note_type=payload.note_type,
        title=payload.title,
        body=payload.body,
        note_date=payload.note_date,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record)
