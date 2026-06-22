"""expand debt tracking

Revision ID: 5d71c8a4f023
Revises: 9f2a6e51c431
Create Date: 2026-06-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5d71c8a4f023"
down_revision: Union[str, Sequence[str], None] = "9f2a6e51c431"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "debts",
        sa.Column("initial_amount_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "debts",
        sa.Column("minimum_payment_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "debts",
        sa.Column("institution", sa.String(length=160), nullable=False, server_default=""),
    )
    op.add_column(
        "debts",
        sa.Column("debt_type", sa.String(length=60), nullable=False, server_default="other"),
    )
    op.add_column(
        "debts",
        sa.Column("interest_rate_bps", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("UPDATE debts SET initial_amount_cents = current_amount_cents")


def downgrade() -> None:
    op.drop_column("debts", "interest_rate_bps")
    op.drop_column("debts", "debt_type")
    op.drop_column("debts", "institution")
    op.drop_column("debts", "minimum_payment_cents")
    op.drop_column("debts", "initial_amount_cents")
