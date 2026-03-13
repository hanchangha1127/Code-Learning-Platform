"""expand problem kinds and add bridge payload columns

Revision ID: e6f4b7a9c812
Revises: c3b7d2e9f14a
Create Date: 2026-03-06 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f4b7a9c812"
down_revision: Union[str, Sequence[str], None] = "c3b7d2e9f14a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM(
            'coding',
            'analysis',
            'code_block',
            'code_arrange',
            'code_calc',
            'code_error',
            'auditor',
            'context_inference',
            'refactoring_choice',
            'code_blame'
        )
        NOT NULL
        """
    )
    op.add_column("problems", sa.Column("external_id", sa.String(length=128), nullable=True))
    op.add_column("problems", sa.Column("problem_payload", sa.JSON(), nullable=True))
    op.add_column("problems", sa.Column("answer_payload", sa.JSON(), nullable=True))
    op.create_index("ix_problems_external_id", "problems", ["external_id"], unique=False)

    op.add_column("submissions", sa.Column("submission_payload", sa.JSON(), nullable=True))
    op.add_column("ai_analyses", sa.Column("result_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_analyses", "result_payload")
    op.drop_column("submissions", "submission_payload")

    op.drop_index("ix_problems_external_id", table_name="problems")
    op.drop_column("problems", "answer_payload")
    op.drop_column("problems", "problem_payload")
    op.drop_column("problems", "external_id")
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM(
            'coding',
            'code_block',
            'auditor',
            'context_inference',
            'refactoring_choice',
            'code_blame'
        )
        NOT NULL
        """
    )
