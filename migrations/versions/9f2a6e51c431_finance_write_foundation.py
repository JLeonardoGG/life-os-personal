"""finance write foundation

Revision ID: 9f2a6e51c431
Revises: 40450f8b5d64
Create Date: 2026-06-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f2a6e51c431"
down_revision: Union[str, Sequence[str], None] = "40450f8b5d64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("idempotency_key", sa.String(length=160), nullable=True))
    op.create_index(
        "ix_transactions_idempotency_key",
        "transactions",
        ["idempotency_key"],
        unique=True,
    )
    op.create_table(
        "transaction_revisions",
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("legacy_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_key"),
    )
    op.create_index(
        "ix_transaction_revisions_transaction_id",
        "transaction_revisions",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_revisions_idempotency_key",
        "transaction_revisions",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_revisions_idempotency_key", table_name="transaction_revisions")
    op.drop_index("ix_transaction_revisions_transaction_id", table_name="transaction_revisions")
    op.drop_table("transaction_revisions")
    op.drop_index("ix_transactions_idempotency_key", table_name="transactions")
    op.drop_column("transactions", "idempotency_key")
