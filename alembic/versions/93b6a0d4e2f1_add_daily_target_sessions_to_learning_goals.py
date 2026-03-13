"""add daily target sessions to learning goals

Revision ID: 93b6a0d4e2f1
Revises: 7f8a9c2d1e34
Create Date: 2026-03-06 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "93b6a0d4e2f1"
down_revision: Union[str, Sequence[str], None] = "7f8a9c2d1e34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_learning_goals",
        sa.Column("daily_target_sessions", sa.Integer(), nullable=False, server_default="10"),
    )
    op.execute(
        """
        UPDATE user_learning_goals
        SET daily_target_sessions = weekly_target_sessions
        """
    )


def downgrade() -> None:
    op.drop_column("user_learning_goals", "daily_target_sessions")
