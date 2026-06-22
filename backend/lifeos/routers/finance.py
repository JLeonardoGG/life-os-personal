from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from lifeos.database import get_db
from lifeos.models import (
    Account,
    Budget,
    Debt,
    DebtMovement,
    Investment,
    Subscription,
    Transaction,
    TransactionRevision,
)
from lifeos.schemas import (
    AccountCreate,
    BudgetCreate,
    BudgetUpdate,
    DebtCreate,
    DebtMovementCreate,
    DebtUpdate,
    InvestmentCreate,
    InvestmentUpdate,
    Page,
    SubscriptionCreate,
    SubscriptionUpdate,
    TransactionCreate,
    TransactionUpdate,
)
from lifeos.security import require_session_or_api_key
from lifeos.serializers import model_dict, to_cents

router = APIRouter(
    prefix="/api",
    tags=["finance"],
    dependencies=[Depends(require_session_or_api_key)],
)


def _active(model):
    return model.deleted_at.is_(None)


def _get_or_404(db: Session, model, record_id: str):
    record = db.scalar(select(model).where(model.id == record_id, _active(model)))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


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


def _transaction_dict(record: Transaction) -> dict:
    return model_dict(record, {"amount_cents": "amount"})


def _transaction_revision(
    db: Session,
    record: Transaction,
    action: str,
    idempotency_key: str | None,
) -> None:
    db.add(
        TransactionRevision(
            transaction_id=record.id,
            action=action,
            idempotency_key=idempotency_key,
            snapshot=_transaction_dict(record),
        )
    )


def _validate_account(db: Session, account_id: str | None) -> None:
    if not account_id:
        return
    account = db.scalar(select(Account.id).where(Account.id == account_id, _active(Account)))
    if not account:
        raise HTTPException(status_code=422, detail="Account not found")


def _budget_dict(record: Budget) -> dict:
    result = model_dict(
        record,
        {
            "income_target_cents": "income_target",
            "expense_limit_cents": "expense_limit",
            "savings_target_cents": "savings_target",
        },
    )
    result["category_limits"] = {
        key: amount / 100 for key, amount in (record.category_limits or {}).items()
    }
    return result


def _subscription_next_due(record: Subscription, today: date | None = None) -> date:
    current = today or date.today()
    year = current.year
    month = current.month
    if record.frequency == "yearly":
        month = record.billing_month or current.month
        if (month, record.billing_day) < (current.month, current.day):
            year += 1
    elif record.billing_day < current.day:
        month += 1
        if month > 12:
            month = 1
            year += 1
    day = min(record.billing_day, monthrange(year, month)[1])
    return date(year, month, day)


def _subscription_dict(record: Subscription) -> dict:
    result = model_dict(record, {"amount_cents": "amount"})
    result["next_due_date"] = _subscription_next_due(record).isoformat()
    return result


def _debt_dict(record: Debt) -> dict:
    result = model_dict(
        record,
        {
            "initial_amount_cents": "initial_amount",
            "current_amount_cents": "amount",
            "minimum_payment_cents": "minimum_payment",
        },
    )
    result["interest_rate"] = record.interest_rate_bps / 100
    return result


def _debt_movement_increases_balance(kind: str) -> bool:
    return kind not in {
        "payment",
        "debt_payment",
        "receivable_payment",
        "adjustment_negative",
    }


@router.get("/accounts", response_model=Page)
def list_accounts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Account).where(_active(Account)).order_by(Account.name)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return Page(items=[model_dict(item) for item in records], total=total, limit=limit, offset=offset)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> dict:
    record = Account(
        name=payload.name,
        institution=payload.institution,
        account_type=payload.account_type,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record)


@router.get("/transactions", response_model=Page)
def list_transactions(
    start_date: date | None = None,
    end_date: date | None = None,
    type: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Transaction).where(_active(Transaction))
    if start_date:
        query = query.where(Transaction.date >= start_date)
    if end_date:
        query = query.where(Transaction.date <= end_date)
    if type:
        query = query.where(Transaction.type == type)
    if category:
        query = query.where(Transaction.category == category)
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    query = query.order_by(Transaction.date.desc(), Transaction.created_at.desc())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    items = [model_dict(item, {"amount_cents": "amount"}) for item in records]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    existing = db.scalar(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.deleted_at is not None:
            raise HTTPException(status_code=409, detail="Idempotency-Key belongs to a deleted transaction")
        return _transaction_dict(existing)
    _validate_account(db, payload.account_id)
    record = Transaction(
        date=payload.date,
        type=payload.type,
        category=payload.category,
        name=payload.name,
        description=payload.description,
        amount_cents=to_cents(payload.amount),
        expense_nature=payload.expense_nature,
        source=payload.source,
        source_hash=payload.source_hash,
        idempotency_key=idempotency_key,
        account_id=payload.account_id,
        details=payload.metadata,
    )
    try:
        db.add(record)
        db.flush()
        _transaction_revision(db, record, "create", idempotency_key)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        )
        if existing and existing.deleted_at is None:
            return _transaction_dict(existing)
        raise HTTPException(
            status_code=409,
            detail="Transaction conflicts with an existing record",
        ) from None
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaction could not be saved") from error
    return _transaction_dict(record)


@router.put("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, Transaction, transaction_id)
    data = payload.model_dump(exclude_unset=True)
    if "account_id" in data:
        _validate_account(db, data["account_id"])
    before = _transaction_dict(record)
    if "amount" in data:
        record.amount_cents = to_cents(data.pop("amount"))
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    try:
        db.add(
            TransactionRevision(
                transaction_id=record.id,
                action="update",
                idempotency_key=idempotency_key,
                snapshot=before,
            )
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Transaction conflicts with an existing record",
        ) from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaction could not be updated") from error
    return _transaction_dict(record)


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: str,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> None:
    record = db.scalar(select(Transaction).where(Transaction.id == transaction_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is not None:
        return
    _transaction_revision(db, record, "delete", idempotency_key)
    record.deleted_at = datetime.now(UTC)
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaction could not be deleted") from error


@router.post("/transactions/{transaction_id}/restore")
def restore_transaction(
    transaction_id: str,
    idempotency_key: str | None = Depends(_optional_idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    record = db.scalar(select(Transaction).where(Transaction.id == transaction_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is None:
        return _transaction_dict(record)
    record.deleted_at = None
    try:
        db.flush()
        _transaction_revision(db, record, "restore", idempotency_key)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaction could not be restored") from error
    return _transaction_dict(record)


@router.get("/transactions/{transaction_id}/history", response_model=Page)
def transaction_history(
    transaction_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    if not db.scalar(select(Transaction.id).where(Transaction.id == transaction_id)):
        raise HTTPException(status_code=404, detail="Record not found")
    query = (
        select(TransactionRevision)
        .where(TransactionRevision.transaction_id == transaction_id)
        .order_by(TransactionRevision.created_at.desc())
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return Page(
        items=[model_dict(item) for item in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/budgets", response_model=Page)
def list_budgets(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Budget).where(_active(Budget)).order_by(Budget.period.desc())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    items = [_budget_dict(item) for item in records]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/budgets")
def upsert_budget(payload: BudgetCreate, db: Session = Depends(get_db)) -> dict:
    record = db.scalar(select(Budget).where(Budget.period == payload.period))
    category_limits = {key: to_cents(value) for key, value in payload.category_limits.items()}
    if not record:
        record = Budget(period=payload.period)
        db.add(record)
    record.income_target_cents = to_cents(payload.income_target)
    record.expense_limit_cents = to_cents(payload.expense_limit)
    record.savings_target_cents = to_cents(payload.savings_target)
    record.category_limits = category_limits
    record.deleted_at = None
    db.commit()
    return _budget_dict(record)


@router.put("/budgets/{budget_id}")
def update_budget(
    budget_id: str,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, Budget, budget_id)
    data = payload.model_dump(exclude_unset=True)
    if "period" in data:
        duplicate = db.scalar(
            select(Budget.id).where(
                Budget.period == data["period"],
                Budget.id != budget_id,
                _active(Budget),
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Budget period already exists")
    money_fields = {
        "income_target": "income_target_cents",
        "expense_limit": "expense_limit_cents",
        "savings_target": "savings_target_cents",
    }
    for source, target in money_fields.items():
        if source in data:
            setattr(record, target, to_cents(data.pop(source)))
    if "category_limits" in data:
        record.category_limits = {
            key: to_cents(value) for key, value in data.pop("category_limits").items()
        }
    for key, value in data.items():
        setattr(record, key, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Budget period already exists") from error
    return _budget_dict(record)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: str, db: Session = Depends(get_db)) -> None:
    record = db.scalar(select(Budget).where(Budget.id == budget_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is None:
        record.deleted_at = datetime.now(UTC)
        db.commit()


@router.get("/debts", response_model=Page)
def list_debts(
    include_archived: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Debt).where(_active(Debt))
    if not include_archived:
        query = query.where(Debt.archived.is_(False))
    query = query.order_by(Debt.entity)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    items = [_debt_dict(item) for item in records]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/debts", status_code=status.HTTP_201_CREATED)
def create_debt(payload: DebtCreate, db: Session = Depends(get_db)) -> dict:
    record = Debt(
        entity=payload.entity,
        direction=payload.direction,
        initial_amount_cents=to_cents(payload.amount),
        current_amount_cents=to_cents(payload.amount),
        minimum_payment_cents=to_cents(payload.minimum_payment),
        institution=payload.institution,
        debt_type=payload.debt_type,
        interest_rate_bps=round(payload.interest_rate * 100),
        due_date=payload.due_date,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    return _debt_dict(record)


@router.put("/debts/{debt_id}")
def update_debt(
    debt_id: str,
    payload: DebtUpdate,
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, Debt, debt_id)
    data = payload.model_dump(exclude_unset=True)
    if "current_amount" in data:
        record.current_amount_cents = to_cents(data.pop("current_amount"))
    if "minimum_payment" in data:
        record.minimum_payment_cents = to_cents(data.pop("minimum_payment"))
    if "interest_rate" in data:
        record.interest_rate_bps = round(data.pop("interest_rate") * 100)
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    return _debt_dict(record)


@router.delete("/debts/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_debt(debt_id: str, db: Session = Depends(get_db)) -> None:
    record = db.scalar(select(Debt).where(Debt.id == debt_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is None:
        record.deleted_at = datetime.now(UTC)
        db.commit()


@router.get("/debts/{debt_id}/movements", response_model=Page)
def list_debt_movements(
    debt_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    _get_or_404(db, Debt, debt_id)
    query = (
        select(DebtMovement)
        .where(DebtMovement.debt_id == debt_id, _active(DebtMovement))
        .order_by(DebtMovement.date.desc(), DebtMovement.created_at.desc())
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return Page(
        items=[model_dict(item, {"amount_cents": "amount"}) for item in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/debts/{debt_id}/movements", status_code=status.HTTP_201_CREATED)
def add_debt_movement(
    debt_id: str,
    payload: DebtMovementCreate,
    db: Session = Depends(get_db),
) -> dict:
    debt = _get_or_404(db, Debt, debt_id)
    cents = to_cents(payload.amount)
    record = DebtMovement(
        debt_id=debt.id,
        date=payload.date,
        kind=payload.kind,
        amount_cents=cents,
        description=payload.description,
        due_date=payload.due_date,
    )
    if _debt_movement_increases_balance(payload.kind):
        debt.current_amount_cents += cents
    else:
        debt.current_amount_cents = max(0, debt.current_amount_cents - cents)
    db.add(record)
    db.commit()
    return model_dict(record, {"amount_cents": "amount"})


@router.delete(
    "/debts/{debt_id}/movements/{movement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_debt_movement(
    debt_id: str,
    movement_id: str,
    db: Session = Depends(get_db),
) -> None:
    debt = _get_or_404(db, Debt, debt_id)
    record = db.scalar(
        select(DebtMovement).where(
            DebtMovement.id == movement_id,
            DebtMovement.debt_id == debt_id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is not None:
        return
    if _debt_movement_increases_balance(record.kind):
        debt.current_amount_cents = max(0, debt.current_amount_cents - record.amount_cents)
    else:
        debt.current_amount_cents += record.amount_cents
    record.deleted_at = datetime.now(UTC)
    db.commit()


@router.get("/subscriptions", response_model=Page)
def list_subscriptions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Subscription).where(_active(Subscription)).order_by(Subscription.name)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    items = [_subscription_dict(item) for item in records]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)) -> dict:
    record = Subscription(
        name=payload.name,
        amount_cents=to_cents(payload.amount),
        category=payload.category,
        billing_day=payload.billing_day,
        frequency=payload.frequency,
        billing_month=payload.billing_month,
        payment_method=payload.payment_method,
        active=payload.active,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    return _subscription_dict(record)


@router.put("/subscriptions/{subscription_id}")
def update_subscription(
    subscription_id: str,
    payload: SubscriptionUpdate,
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, Subscription, subscription_id)
    data = payload.model_dump(exclude_unset=True)
    if "amount" in data:
        record.amount_cents = to_cents(data.pop("amount"))
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    return _subscription_dict(record)


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(subscription_id: str, db: Session = Depends(get_db)) -> None:
    record = db.scalar(select(Subscription).where(Subscription.id == subscription_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is None:
        record.deleted_at = datetime.now(UTC)
        db.commit()


@router.get("/investments", response_model=Page)
def list_investments(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Investment).where(_active(Investment)).order_by(Investment.institution)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return Page(
        items=[model_dict(item, {"amount_cents": "amount"}) for item in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/investments", status_code=status.HTTP_201_CREATED)
def create_investment(payload: InvestmentCreate, db: Session = Depends(get_db)) -> dict:
    record = Investment(
        investment_type=payload.investment_type,
        institution=payload.institution,
        amount_cents=to_cents(payload.amount),
        as_of_date=payload.as_of_date,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record, {"amount_cents": "amount"})


@router.put("/investments/{investment_id}")
def update_investment(
    investment_id: str,
    payload: InvestmentUpdate,
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, Investment, investment_id)
    data = payload.model_dump(exclude_unset=True)
    if "amount" in data:
        record.amount_cents = to_cents(data.pop("amount"))
    if "metadata" in data:
        record.details = data.pop("metadata") or {}
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    return model_dict(record, {"amount_cents": "amount"})


@router.delete("/investments/{investment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_investment(investment_id: str, db: Session = Depends(get_db)) -> None:
    record = db.scalar(select(Investment).where(Investment.id == investment_id))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.deleted_at is None:
        record.deleted_at = datetime.now(UTC)
        db.commit()
