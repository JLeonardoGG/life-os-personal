from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid4_str() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class RecordMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    legacy_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Account(RecordMixin, Base):
    __tablename__ = "accounts"

    name: Mapped[str] = mapped_column(String(160))
    institution: Mapped[str] = mapped_column(String(160), default="")
    account_type: Mapped[str] = mapped_column(String(60), default="other")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Transaction(RecordMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_date_type", "date", "type"),)

    date: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(80), default="Otro", index=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int] = mapped_column(Integer)
    expense_nature: Mapped[str] = mapped_column(String(30), default="")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    source_hash: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class TransactionRevision(RecordMixin, Base):
    __tablename__ = "transaction_revisions"

    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Budget(RecordMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("period", name="uq_budgets_period"),)

    period: Mapped[str] = mapped_column(String(7), index=True)
    income_target_cents: Mapped[int] = mapped_column(Integer, default=0)
    expense_limit_cents: Mapped[int] = mapped_column(Integer, default=0)
    savings_target_cents: Mapped[int] = mapped_column(Integer, default=0)
    category_limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MonthlyClosure(RecordMixin, Base):
    __tablename__ = "monthly_closures"
    __table_args__ = (UniqueConstraint("module", "period", name="uq_monthly_closure"),)

    module: Mapped[str] = mapped_column(String(40), default="finance")
    period: Mapped[str] = mapped_column(String(7), index=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checklist: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Subscription(RecordMixin, Base):
    __tablename__ = "subscriptions"

    name: Mapped[str] = mapped_column(String(180))
    amount_cents: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(80), default="Suscripciones")
    billing_day: Mapped[int] = mapped_column(Integer, default=1)
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")
    billing_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method: Mapped[str] = mapped_column(String(80), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Investment(RecordMixin, Base):
    __tablename__ = "investments"

    investment_type: Mapped[str] = mapped_column(String(80))
    institution: Mapped[str] = mapped_column(String(160))
    amount_cents: Mapped[int] = mapped_column(Integer)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Debt(RecordMixin, Base):
    __tablename__ = "debts"

    entity: Mapped[str] = mapped_column(String(180), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="owed")
    initial_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    current_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    minimum_payment_cents: Mapped[int] = mapped_column(Integer, default=0)
    institution: Mapped[str] = mapped_column(String(160), default="")
    debt_type: Mapped[str] = mapped_column(String(60), default="other")
    interest_rate_bps: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    movements: Mapped[list[DebtMovement]] = relationship(back_populates="debt", cascade="all, delete-orphan")


class DebtMovement(RecordMixin, Base):
    __tablename__ = "debt_movements"

    debt_id: Mapped[str] = mapped_column(ForeignKey("debts.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    amount_cents: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    debt: Mapped[Debt] = relationship(back_populates="movements")


class UploadedFile(RecordMixin, Base):
    __tablename__ = "uploaded_files"

    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    relative_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(60), default="document")
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class TaxDocument(RecordMixin, Base):
    __tablename__ = "tax_documents"
    __table_args__ = (Index("ix_tax_documents_period_kind", "period", "document_kind"),)

    document_kind: Mapped[str] = mapped_column(String(40))
    period: Mapped[str] = mapped_column(String(7), index=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uuid: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    issuer_rfc: Mapped[str] = mapped_column(String(20), default="")
    receiver_rfc: Mapped[str] = mapped_column(String(20), default="")
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_transferred_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_withheld_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="imported")
    source_hash: Mapped[str] = mapped_column(String(64), unique=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("uploaded_files.id"), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TaxEntry(RecordMixin, Base):
    __tablename__ = "tax_entries"

    entry_type: Mapped[str] = mapped_column(String(40), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    concept: Mapped[str] = mapped_column(String(240), default="")
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    withholding_isr_cents: Mapped[int] = mapped_column(Integer, default=0)
    withholding_iva_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Task(RecordMixin, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Event(RecordMixin, Base):
    __tablename__ = "events"

    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence: Mapped[str] = mapped_column(String(40), default="none")
    location: Mapped[str] = mapped_column(String(240), default="")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="active")
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Routine(RecordMixin, Base):
    __tablename__ = "routines"

    routine_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(180))
    schedule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160),
        unique=True,
        nullable=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class HealthLog(RecordMixin, Base):
    __tablename__ = "health_logs"

    log_type: Mapped[str] = mapped_column(String(40), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str] = mapped_column(String(30), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160),
        unique=True,
        nullable=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class CarLog(RecordMixin, Base):
    __tablename__ = "car_logs"

    log_type: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    odometer_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160),
        unique=True,
        nullable=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class CarReminder(RecordMixin, Base):
    __tablename__ = "car_reminders"

    reminder_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(180))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_odometer_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence: Mapped[str] = mapped_column(String(40), default="none")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160),
        unique=True,
        nullable=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Note(RecordMixin, Base):
    __tablename__ = "notes"

    note_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240), default="")
    body: Mapped[str] = mapped_column(Text)
    note_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class DailyReview(RecordMixin, Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (UniqueConstraint("review_date", name="uq_daily_review_date"),)

    review_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class AcademicCourse(RecordMixin, Base):
    __tablename__ = "academic_courses"

    name: Mapped[str] = mapped_column(String(240))
    semester: Mapped[str] = mapped_column(String(40), default="")
    credits: Mapped[int] = mapped_column(Integer, default=0)
    grade: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Project(RecordMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(240))
    project_type: Mapped[str] = mapped_column(String(50), default="personal")
    status: Mapped[str] = mapped_column(String(30), default="idea")
    description: Mapped[str] = mapped_column(Text, default="")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class ImportBatch(RecordMixin, Base):
    __tablename__ = "import_batches"

    source: Mapped[str] = mapped_column(String(60), default="localstorage")
    payload_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="preview")
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    errors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InboxMessage(RecordMixin, Base):
    __tablename__ = "inbox_messages"

    source: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_review", index=True)
    proposed_type: Mapped[str] = mapped_column(String(30), default="note")
    proposed_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confirmed_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class AutomationLog(RecordMixin, Base):
    __tablename__ = "automation_logs"

    source: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(120))
    endpoint: Mapped[str] = mapped_column(String(240), default="")
    result: Mapped[str] = mapped_column(String(30), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    error_message: Mapped[str] = mapped_column(String(500), default="")
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class AppSetting(RecordMixin, Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
