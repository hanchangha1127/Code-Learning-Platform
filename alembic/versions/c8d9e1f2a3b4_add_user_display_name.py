"""add user display name

Revision ID: c8d9e1f2a3b4
Revises: 93b6a0d4e2f1
Create Date: 2026-05-01 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "93b6a0d4e2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
