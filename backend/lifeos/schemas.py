from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Page(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class TransactionCreate(BaseModel):
    date: DateType
    type: Literal["ingreso", "gasto"]
    category: str = "Otro"
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    amount: Decimal = Field(gt=0)
    expense_nature: str = ""
    source: str = "manual"
    account_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransactionUpdate(BaseModel):
    date: DateType | None = None
    type: Literal["ingreso", "gasto"] | None = None
    category: str | None = None
    name: str | None = None
    description: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    expense_nature: str | None = None
    account_id: str | None = None
    metadata: dict[str, Any] | None = None


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    institution: str = ""
    account_type: str = "other"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetCreate(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    income_target: Decimal = 0
    expense_limit: Decimal = 0
    savings_target: Decimal = 0
    category_limits: dict[str, Decimal] = Field(default_factory=dict)


class DebtCreate(BaseModel):
    entity: str = Field(min_length=1, max_length=180)
    direction: Literal["owed", "receivable"] = "owed"
    amount: Decimal = Field(ge=0)
    due_date: DateType | None = None
    status: str = "active"
    notes: str = ""


class DebtMovementCreate(BaseModel):
    date: DateType
    kind: str
    amount: Decimal = Field(gt=0)
    description: str = ""
    due_date: DateType | None = None


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    amount: Decimal = Field(gt=0)
    category: str = "Suscripciones"
    billing_day: int = Field(default=1, ge=1, le=31)
    frequency: Literal["monthly", "yearly"] = "monthly"
    billing_month: int | None = Field(default=None, ge=1, le=12)
    payment_method: str = ""
    active: bool = True
    notes: str = ""


class InvestmentCreate(BaseModel):
    investment_type: str
    institution: str
    amount: Decimal = Field(ge=0)
    as_of_date: DateType | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    priority: Literal["urgente", "normal", "baja"] = "normal"
    due_at: datetime | None = None
    status: str = "pending"
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool = False
    recurrence: str = "none"
    location: str = ""
    source: str = "manual"
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ends_at")
    @classmethod
    def valid_end(cls, value: datetime | None, info):
        starts_at = info.data.get("starts_at")
        if value and starts_at and value < starts_at:
            raise ValueError("ends_at must be after starts_at")
        return value


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool | None = None
    recurrence: str | None = None
    location: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


class RoutineCreate(BaseModel):
    routine_type: str
    name: str
    schedule: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthLogCreate(BaseModel):
    log_type: str
    recorded_at: datetime
    value: float | None = None
    unit: str = ""
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CarLogCreate(BaseModel):
    log_type: str
    date: DateType
    odometer_km: int | None = Field(default=None, ge=0)
    amount: Decimal = Field(default=0, ge=0)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CarReminderCreate(BaseModel):
    reminder_type: str
    title: str
    due_date: DateType | None = None
    due_odometer_km: int | None = Field(default=None, ge=0)
    recurrence: str = "none"
    status: str = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class NoteCreate(BaseModel):
    note_type: str = "note"
    title: str = ""
    body: str = Field(min_length=1)
    note_date: DateType | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboxCreate(BaseModel):
    source: str = "n8n"
    message: str = Field(min_length=1, max_length=5000)
    timestamp: datetime
    external_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
