"""add wrong_answer_types json field to user_problem_stats

Revision ID: d7a6c9b14e2f
Revises: bcebd7111fc8
Create Date: 2026-02-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7a6c9b14e2f"
down_revision: Union[str, Sequence[str], None] = "bcebd7111fc8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_problem_stats", sa.Column("wrong_answer_types", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_problem_stats", "wrong_answer_types")
