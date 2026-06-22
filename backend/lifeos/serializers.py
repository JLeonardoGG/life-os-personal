from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.inspection import inspect


def to_cents(value: Decimal | float | int | str | None) -> int:
    decimal_value = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(decimal_value * 100)


def from_cents(value: int | None) -> float:
    return float(Decimal(value or 0) / 100)


def model_dict(model, money_fields: dict[str, str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in inspect(model).mapper.column_attrs:
        value = getattr(model, column.key)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        result[column.key] = value
    for source, target in (money_fields or {}).items():
        result[target] = from_cents(result.pop(source, 0))
    return result
