from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifeos.database import get_db
from lifeos.models import CarLog, CarReminder, Event, HealthLog, Note, Routine, Task
from lifeos.schemas import (
    CarLogCreate,
    CarReminderCreate,
    EventCreate,
    EventUpdate,
    HealthLogCreate,
    NoteCreate,
    Page,
    RoutineCreate,
    TaskCreate,
    TaskUpdate,
)
from lifeos.security import require_session_or_api_key
from lifeos.serializers import model_dict, to_cents

router = APIRouter(
    prefix="/api",
    tags=["life"],
    dependencies=[Depends(require_session_or_api_key)],
)


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
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    return _page(
        db,
        select(Routine).where(_active(Routine)).order_by(Routine.routine_type, Routine.name),
        limit,
        offset,
    )


@router.post("/routines", status_code=status.HTTP_201_CREATED)
def create_routine(payload: RoutineCreate, db: Session = Depends(get_db)) -> dict:
    record = Routine(
        routine_type=payload.routine_type,
        name=payload.name,
        schedule=payload.schedule,
        active=payload.active,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record)


@router.post("/health/log", status_code=status.HTTP_201_CREATED)
def create_health_log(payload: HealthLogCreate, db: Session = Depends(get_db)) -> dict:
    record = HealthLog(
        log_type=payload.log_type,
        recorded_at=payload.recorded_at,
        value=payload.value,
        unit=payload.unit,
        notes=payload.notes,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record)


@router.get("/health/stats")
def health_stats(
    log_type: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    query = select(HealthLog).where(_active(HealthLog))
    if log_type:
        query = query.where(HealthLog.log_type == log_type)
    records = db.scalars(query.order_by(HealthLog.recorded_at.desc()).limit(365)).all()
    values = [item.value for item in records if item.value is not None]
    return {
        "count": len(records),
        "average": sum(values) / len(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "latest": model_dict(records[0]) if records else None,
    }


@router.get("/car/logs", response_model=Page)
def list_car_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    return _page(
        db,
        select(CarLog).where(_active(CarLog)).order_by(CarLog.date.desc()),
        limit,
        offset,
        {"amount_cents": "amount"},
    )


@router.post("/car/logs", status_code=status.HTTP_201_CREATED)
def create_car_log(payload: CarLogCreate, db: Session = Depends(get_db)) -> dict:
    record = CarLog(
        log_type=payload.log_type,
        date=payload.date,
        odometer_km=payload.odometer_km,
        amount_cents=to_cents(payload.amount),
        description=payload.description,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record, {"amount_cents": "amount"})


@router.get("/car/reminders", response_model=Page)
def list_car_reminders(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    return _page(
        db,
        select(CarReminder).where(_active(CarReminder)).order_by(CarReminder.due_date.asc()),
        limit,
        offset,
    )


@router.post("/car/reminders", status_code=status.HTTP_201_CREATED)
def create_car_reminder(payload: CarReminderCreate, db: Session = Depends(get_db)) -> dict:
    record = CarReminder(
        reminder_type=payload.reminder_type,
        title=payload.title,
        due_date=payload.due_date,
        due_odometer_km=payload.due_odometer_km,
        recurrence=payload.recurrence,
        status=payload.status,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record)


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
