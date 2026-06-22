from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from lifeos import __version__
from lifeos.config import Settings, get_settings
from lifeos.database import get_db
from lifeos.models import Event, Task, Transaction
from lifeos.security import create_local_session, require_session_or_api_key
from lifeos.serializers import from_cents, model_dict

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "version": __version__,
        "time": datetime.now(UTC).isoformat(),
        "database": "ok",
        "ai_enabled": settings.ai_enabled,
        "host": settings.host,
        "port": settings.port,
        "data_dir": str(settings.data_dir),
        "client": request.client.host if request.client else None,
    }


@router.post("/session")
def session(payload: dict = Depends(create_local_session)) -> dict:
    return payload


def _summary(db: Session, start_date: date, end_date: date) -> dict:
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.deleted_at.is_(None),
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
    ).all()
    income = sum(item.amount_cents for item in transactions if item.type == "ingreso")
    expense = sum(item.amount_cents for item in transactions if item.type == "gasto")
    tz = ZoneInfo("America/Mexico_City")
    start_at = datetime.combine(start_date, time.min, tzinfo=tz)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    tasks = db.scalars(
        select(Task).where(
            Task.deleted_at.is_(None),
            Task.status != "done",
            Task.due_at.is_not(None),
            Task.due_at < end_at,
        )
    ).all()
    events = db.scalars(
        select(Event).where(
            Event.deleted_at.is_(None),
            Event.starts_at >= start_at,
            Event.starts_at < end_at,
        )
    ).all()
    return {
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "finance": {
            "income": from_cents(income),
            "expense": from_cents(expense),
            "balance": from_cents(income - expense),
            "transaction_count": len(transactions),
        },
        "tasks": {
            "open_due_count": len(tasks),
            "urgent_count": sum(item.priority == "urgente" for item in tasks),
            "items": [model_dict(item) for item in tasks[:10]],
        },
        "events": {
            "count": len(events),
            "items": [model_dict(item) for item in events[:10]],
        },
    }


@router.get("/summary/today", dependencies=[Depends(require_session_or_api_key)])
def summary_today(db: Session = Depends(get_db)) -> dict:
    today = datetime.now(ZoneInfo("America/Mexico_City")).date()
    return _summary(db, today, today)


@router.get("/summary/week", dependencies=[Depends(require_session_or_api_key)])
def summary_week(db: Session = Depends(get_db)) -> dict:
    today = datetime.now(ZoneInfo("America/Mexico_City")).date()
    start = today - timedelta(days=today.weekday())
    return _summary(db, start, start + timedelta(days=6))


@router.get("/summary/month", dependencies=[Depends(require_session_or_api_key)])
def summary_month(db: Session = Depends(get_db)) -> dict:
    today = datetime.now(ZoneInfo("America/Mexico_City")).date()
    start = today.replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return _summary(db, start, next_month - timedelta(days=1))
