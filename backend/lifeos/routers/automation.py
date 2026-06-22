from __future__ import annotations

import time
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifeos.database import get_db
from lifeos.models import AutomationLog, Event, InboxMessage, Note, Task, Transaction
from lifeos.schemas import InboxCreate, Page
from lifeos.security import require_api_key
from lifeos.serializers import model_dict, to_cents
from lifeos.services.classifier import classify_message

router = APIRouter(
    prefix="/api",
    tags=["automation"],
    dependencies=[Depends(require_api_key)],
)


def _required_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not idempotency_key or len(idempotency_key) > 160:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key header is required")
    return idempotency_key


def _log(
    db: Session,
    *,
    source: str,
    action: str,
    endpoint: str,
    result: str,
    started: float,
    idempotency_key: str,
    entity_id: str | None = None,
    error_code: str = "",
    error_message: str = "",
    details: dict | None = None,
) -> None:
    db.add(
        AutomationLog(
            source=source,
            action=action,
            endpoint=endpoint,
            result=result,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            idempotency_key=idempotency_key,
            entity_id=entity_id,
            error_code=error_code,
            error_message=error_message[:500],
            details=details or {},
        )
    )


@router.post("/inbox/message", status_code=status.HTTP_202_ACCEPTED)
def receive_inbox_message(
    payload: InboxCreate,
    idempotency_key: str = Depends(_required_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    started = time.monotonic()
    existing = db.scalar(select(InboxMessage).where(InboxMessage.idempotency_key == idempotency_key))
    if existing:
        return model_dict(existing)
    classification = classify_message(payload.message, payload.timestamp)
    record = InboxMessage(
        source=payload.source,
        message=payload.message,
        received_at=payload.timestamp,
        external_id=payload.external_id,
        idempotency_key=idempotency_key,
        status="pending_review",
        proposed_type=classification["type"],
        proposed_payload=classification["payload"],
        details={
            **payload.metadata,
            "confidence": classification["confidence"],
            "rule": classification["rule"],
        },
    )
    db.add(record)
    db.flush()
    _log(
        db,
        source=payload.source,
        action="inbox.receive",
        endpoint="/api/inbox/message",
        result="accepted",
        started=started,
        idempotency_key=idempotency_key,
        entity_id=record.id,
        details={"proposed_type": record.proposed_type},
    )
    db.commit()
    return model_dict(record)


@router.get("/inbox/messages", response_model=Page)
def list_inbox_messages(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(InboxMessage).where(InboxMessage.deleted_at.is_(None))
    if status_filter:
        query = query.where(InboxMessage.status == status_filter)
    query = query.order_by(InboxMessage.received_at.desc())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return Page(
        items=[model_dict(item) for item in records],
        total=total,
        limit=limit,
        offset=offset,
    )


def _create_confirmed_entity(db: Session, message: InboxMessage):
    payload = message.proposed_payload or {}
    if message.proposed_type == "expense":
        record = Transaction(
            date=date.fromisoformat(payload.get("date")),
            type="gasto",
            category=payload.get("category") or "Otro",
            name=payload.get("name") or message.message,
            description="",
            amount_cents=to_cents(payload.get("amount")),
            source="inbox",
            details={"inbox_message_id": message.id},
        )
    elif message.proposed_type in {"task", "reminder"}:
        due_at = datetime.fromisoformat(payload["due_at"]) if payload.get("due_at") else None
        record = Task(
            title=payload.get("title") or message.message,
            priority=payload.get("priority") or "normal",
            due_at=due_at,
            status="pending",
            source="inbox",
            details={"inbox_message_id": message.id, "reminder": message.proposed_type == "reminder"},
        )
    elif message.proposed_type == "event":
        record = Event(
            title=payload.get("title") or message.message,
            starts_at=datetime.fromisoformat(payload["starts_at"]),
            source="inbox",
            details={"inbox_message_id": message.id},
        )
    else:
        record = Note(
            note_type=payload.get("note_type") or "inbox",
            title=payload.get("title") or "Mensaje recibido",
            body=payload.get("body") or message.message,
            note_date=message.received_at.date(),
            details={"inbox_message_id": message.id},
        )
    db.add(record)
    db.flush()
    return record


@router.post("/inbox/messages/{message_id}/confirm")
def confirm_inbox_message(
    message_id: str,
    idempotency_key: str = Depends(_required_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    started = time.monotonic()
    message = db.scalar(select(InboxMessage).where(InboxMessage.id == message_id))
    if not message:
        raise HTTPException(status_code=404, detail="Inbox message not found")
    if message.status == "confirmed":
        return model_dict(message)
    if message.status == "rejected":
        raise HTTPException(status_code=409, detail="Rejected messages cannot be confirmed")
    record = _create_confirmed_entity(db, message)
    message.status = "confirmed"
    message.confirmed_entity_id = record.id
    _log(
        db,
        source=message.source,
        action="inbox.confirm",
        endpoint=f"/api/inbox/messages/{message_id}/confirm",
        result="confirmed",
        started=started,
        idempotency_key=idempotency_key,
        entity_id=record.id,
        details={"entity_type": message.proposed_type},
    )
    db.commit()
    return model_dict(message)


@router.post("/inbox/messages/{message_id}/reject")
def reject_inbox_message(
    message_id: str,
    idempotency_key: str = Depends(_required_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    started = time.monotonic()
    message = db.scalar(select(InboxMessage).where(InboxMessage.id == message_id))
    if not message:
        raise HTTPException(status_code=404, detail="Inbox message not found")
    if message.status == "confirmed":
        raise HTTPException(status_code=409, detail="Confirmed messages cannot be rejected")
    message.status = "rejected"
    _log(
        db,
        source=message.source,
        action="inbox.reject",
        endpoint=f"/api/inbox/messages/{message_id}/reject",
        result="rejected",
        started=started,
        idempotency_key=idempotency_key,
        entity_id=message.id,
    )
    db.commit()
    return model_dict(message)


@router.get("/automation/logs", response_model=Page)
def automation_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(AutomationLog).order_by(AutomationLog.created_at.desc())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return Page(
        items=[model_dict(item) for item in records],
        total=total,
        limit=limit,
        offset=offset,
    )
