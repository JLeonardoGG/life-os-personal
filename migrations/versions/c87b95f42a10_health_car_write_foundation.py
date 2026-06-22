"""health and car write foundation

Revision ID: c87b95f42a10
Revises: 5d71c8a4f023
Create Date: 2026-06-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c87b95f42a10"
down_revision: Union[str, Sequence[str], None] = "5d71c8a4f023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("routines", "health_logs", "car_logs", "car_reminders")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        )
        op.create_index(
            f"ix_{table}_idempotency_key",
            table,
            ["idempotency_key"],
            unique=True,
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_idempotency_key", table_name=table)
        op.drop_column(table, "idempotency_key")
