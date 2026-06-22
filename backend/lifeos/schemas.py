from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Page(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class TransactionCreate(BaseModel):
    date: DateType
    type: Literal["ingreso", "gasto", "transferencia", "ajuste"]
    category: str = "Otro"
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    expense_nature: str = ""
    source: Literal["manual", "import", "migration", "inbox", "frontend", "statement"] = "manual"
    account_id: str | None = None
    source_hash: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        aliases = {
            "income": "ingreso",
            "expense": "gasto",
            "transfer": "transferencia",
            "adjustment": "ajuste",
        }
        return aliases.get(str(value).lower(), value)


class TransactionUpdate(BaseModel):
    date: DateType | None = None
    type: Literal["ingreso", "gasto", "transferencia", "ajuste"] | None = None
    category: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    expense_nature: str | None = None
    source: Literal["manual", "import", "migration", "inbox", "frontend", "statement"] | None = None
    account_id: str | None = None
    source_hash: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] | None = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        aliases = {
            "income": "ingreso",
            "expense": "gasto",
            "transfer": "transferencia",
            "adjustment": "ajuste",
        }
        return aliases.get(str(value).lower(), value)


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    institution: str = ""
    account_type: str = "other"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetCreate(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    income_target: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    expense_limit: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    savings_target: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    category_limits: dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("category_limits")
    @classmethod
    def valid_category_limits(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(amount < 0 for amount in value.values()):
            raise ValueError("category limits cannot be negative")
        return value


class BudgetUpdate(BaseModel):
    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    income_target: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    expense_limit: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    savings_target: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    category_limits: dict[str, Decimal] | None = None

    @field_validator("category_limits")
    @classmethod
    def valid_category_limits(
        cls,
        value: dict[str, Decimal] | None,
    ) -> dict[str, Decimal] | None:
        if value is not None and any(amount < 0 for amount in value.values()):
            raise ValueError("category limits cannot be negative")
        return value


class DebtCreate(BaseModel):
    entity: str = Field(min_length=1, max_length=180)
    direction: Literal["owed", "receivable"] = "owed"
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    minimum_payment: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    institution: str = Field(default="", max_length=160)
    debt_type: str = Field(default="other", max_length=60)
    interest_rate: Decimal = Field(default=0, ge=0, le=1000, decimal_places=2)
    due_date: DateType | None = None
    status: str = "active"
    notes: str = ""


class DebtUpdate(BaseModel):
    entity: str | None = Field(default=None, min_length=1, max_length=180)
    direction: Literal["owed", "receivable"] | None = None
    current_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    minimum_payment: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    institution: str | None = Field(default=None, max_length=160)
    debt_type: str | None = Field(default=None, max_length=60)
    interest_rate: Decimal | None = Field(default=None, ge=0, le=1000, decimal_places=2)
    due_date: DateType | None = None
    status: str | None = None
    archived: bool | None = None
    notes: str | None = None


class DebtMovementCreate(BaseModel):
    date: DateType
    kind: Literal[
        "new_debt",
        "debt_payment",
        "receivable",
        "receivable_payment",
        "interest",
        "charge",
        "adjustment_positive",
        "adjustment_negative",
        "payment",
    ]
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
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


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    category: str | None = None
    billing_day: int | None = Field(default=None, ge=1, le=31)
    frequency: Literal["monthly", "yearly"] | None = None
    billing_month: int | None = Field(default=None, ge=1, le=12)
    payment_method: str | None = None
    active: bool | None = None
    notes: str | None = None


class InvestmentCreate(BaseModel):
    investment_type: str = Field(min_length=1, max_length=80)
    institution: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of_date: DateType | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvestmentUpdate(BaseModel):
    investment_type: str | None = Field(default=None, min_length=1, max_length=80)
    institution: str | None = Field(default=None, min_length=1, max_length=160)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    as_of_date: DateType | None = None
    metadata: dict[str, Any] | None = None


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
    routine_type: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    schedule: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoutineUpdate(BaseModel):
    routine_type: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=180)
    schedule: dict[str, Any] | None = None
    active: bool | None = None
    metadata: dict[str, Any] | None = None


class HealthLogCreate(BaseModel):
    log_type: str = Field(min_length=1, max_length=40)
    recorded_at: datetime
    value: float | None = None
    unit: str = Field(default="", max_length=30)
    notes: str = Field(default="", max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_health_value(self):
        validate_health_range(self.log_type, self.value)
        return self


class HealthLogUpdate(BaseModel):
    log_type: str | None = Field(default=None, min_length=1, max_length=40)
    recorded_at: datetime | None = None
    value: float | None = None
    unit: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_health_value(self):
        if self.log_type is not None:
            validate_health_range(self.log_type, self.value)
        elif self.value is not None and self.value < 0:
            raise ValueError("health values cannot be negative")
        return self


def validate_health_range(log_type: str, value: float | None) -> None:
    if value is None:
        return
    normalized = log_type.lower()
    if normalized in {"body", "weight", "peso"} and not 0 < value <= 1000:
        raise ValueError("weight must be greater than 0 and at most 1000 kg")
    if normalized in {"water", "daily_health"} and not 0 <= value <= 100:
        raise ValueError("water must be between 0 and 100")
    if normalized in {"sleep", "wellbeing"} and not 0 <= value <= 48:
        raise ValueError("sleep must be between 0 and 48 hours")
    if normalized in {"exercise", "gym", "cardio"} and not 0 <= value <= 1440:
        raise ValueError("exercise duration must be between 0 and 1440 minutes")
    if value < 0:
        raise ValueError("health values cannot be negative")


class CarLogCreate(BaseModel):
    log_type: str = Field(min_length=1, max_length=40)
    date: DateType
    odometer_km: int | None = Field(default=None, ge=0)
    amount: Decimal = Field(default=0, ge=0)
    description: str = Field(default="", max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CarLogUpdate(BaseModel):
    log_type: str | None = Field(default=None, min_length=1, max_length=40)
    date: DateType | None = None
    odometer_km: int | None = Field(default=None, ge=0)
    amount: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] | None = None


class CarReminderCreate(BaseModel):
    reminder_type: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=180)
    due_date: DateType | None = None
    due_odometer_km: int | None = Field(default=None, ge=0)
    recurrence: str = Field(default="none", max_length=40)
    status: str = Field(default="pending", max_length=30)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CarReminderUpdate(BaseModel):
    reminder_type: str | None = Field(default=None, min_length=1, max_length=60)
    title: str | None = Field(default=None, min_length=1, max_length=180)
    due_date: DateType | None = None
    due_odometer_km: int | None = Field(default=None, ge=0)
    recurrence: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=30)
    metadata: dict[str, Any] | None = None


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
