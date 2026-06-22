from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
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
)
from lifeos.schemas import (
    AccountCreate,
    BudgetCreate,
    DebtCreate,
    DebtMovementCreate,
    InvestmentCreate,
    Page,
    SubscriptionCreate,
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
    query = query.order_by(Transaction.date.desc(), Transaction.created_at.desc())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    items = [model_dict(item, {"amount_cents": "amount"}) for item in records]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)) -> dict:
    record = Transaction(
        date=payload.date,
        type=payload.type,
        category=payload.category,
        name=payload.name,
        description=payload.description,
        amount_cents=to_cents(payload.amount),
        expense_nature=payload.expense_nature,
        source=payload.source,
        account_id=payload.account_id,
        details=payload.metadata,
    )
    db.add(record)
    db.commit()
    return model_dict(record, {"amount_cents": "amount"})


@router.put("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
) -> dict:
    record = _get_or_404(db, Transaction, transaction_id)
    data = payload.model_dump(exclude_unset=True)
    if "amount" in data:
        record.amount_cents = to_cents(data.pop("amount"))
    if "metadata" in data:
        record.details = data.pop("metadata")
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    return model_dict(record, {"amount_cents": "amount"})


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: str, db: Session = Depends(get_db)) -> None:
    record = _get_or_404(db, Transaction, transaction_id)
    record.deleted_at = datetime.now(UTC)
    db.commit()


@router.get("/budgets", response_model=Page)
def list_budgets(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Budget).where(_active(Budget)).order_by(Budget.period.desc())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    items = [
        model_dict(
            item,
            {
                "income_target_cents": "income_target",
                "expense_limit_cents": "expense_limit",
                "savings_target_cents": "savings_target",
            },
        )
        for item in records
    ]
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
    return model_dict(
        record,
        {
            "income_target_cents": "income_target",
            "expense_limit_cents": "expense_limit",
            "savings_target_cents": "savings_target",
        },
    )


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
    items = [model_dict(item, {"current_amount_cents": "amount"}) for item in records]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/debts", status_code=status.HTTP_201_CREATED)
def create_debt(payload: DebtCreate, db: Session = Depends(get_db)) -> dict:
    record = Debt(
        entity=payload.entity,
        direction=payload.direction,
        current_amount_cents=to_cents(payload.amount),
        due_date=payload.due_date,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    return model_dict(record, {"current_amount_cents": "amount"})


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
    if payload.kind in {"payment", "debt_payment", "receivable_payment"}:
        debt.current_amount_cents = max(0, debt.current_amount_cents - cents)
    else:
        debt.current_amount_cents += cents
    db.add(record)
    db.commit()
    return model_dict(record, {"amount_cents": "amount"})


@router.get("/subscriptions", response_model=Page)
def list_subscriptions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Subscription).where(_active(Subscription)).order_by(Subscription.name)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.offset(offset).limit(limit)).all()
    items = [model_dict(item, {"amount_cents": "amount"}) for item in records]
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
    return model_dict(record, {"amount_cents": "amount"})


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
