from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from lifeos.config import get_settings
from lifeos.database import Database
from lifeos.models import Budget, Event, Investment, Subscription, Task, Transaction


def seed_demo(output: Path, force: bool = False) -> Path:
    settings = get_settings()
    output = output.expanduser().resolve()
    if output == settings.database_path.resolve():
        raise RuntimeError("El seed demo nunca puede escribirse sobre la base personal.")
    if output.exists() and not force:
        raise RuntimeError(f"Ya existe {output}. Usa --force para recrearla.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    database = Database(output)
    database.create_schema()
    tz = ZoneInfo("America/Mexico_City")
    with database.session() as db:
        db.add_all(
            [
                Transaction(
                    date=date(2026, 6, 15),
                    type="ingreso",
                    category="Salario",
                    name="Ingreso demo",
                    amount_cents=1200000,
                    source="demo",
                ),
                Transaction(
                    date=date(2026, 6, 16),
                    type="gasto",
                    category="Transporte",
                    name="Gasolina demo",
                    amount_cents=65000,
                    source="demo",
                ),
                Budget(
                    period="2026-06",
                    income_target_cents=1500000,
                    expense_limit_cents=900000,
                    savings_target_cents=600000,
                    category_limits={"Transporte": 150000, "Comida": 250000},
                ),
                Subscription(
                    name="Streaming demo",
                    amount_cents=14900,
                    billing_day=10,
                    payment_method="Tarjeta demo",
                ),
                Investment(
                    investment_type="Renta fija",
                    institution="Institucion demo",
                    amount_cents=2500000,
                ),
                Task(
                    title="Revisar presupuesto demo",
                    priority="normal",
                    due_at=datetime(2026, 6, 22, 18, 0, tzinfo=tz),
                    source="demo",
                ),
                Event(
                    title="Sesion de planeacion demo",
                    starts_at=datetime(2026, 6, 23, 9, 0, tzinfo=tz),
                    ends_at=datetime(2026, 6, 23, 10, 0, tzinfo=tz),
                    source="demo",
                ),
            ]
        )
        db.commit()
    database.engine.dispose()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera una base Life OS con datos falsos.")
    parser.add_argument("--output", type=Path, default=Path("demo/lifeos-demo.db"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(f"Base demo creada: {seed_demo(args.output, args.force)}")
