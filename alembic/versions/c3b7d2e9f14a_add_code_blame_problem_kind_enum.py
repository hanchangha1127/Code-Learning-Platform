"""add code_blame to problem_kind enum

Revision ID: c3b7d2e9f14a
Revises: a1f5d8e7c9ab
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3b7d2e9f14a"
down_revision: Union[str, Sequence[str], None] = "a1f5d8e7c9ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block','auditor','context_inference','refactoring_choice','code_blame')
        NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block','auditor','context_inference','refactoring_choice')
        NOT NULL
        """
    )
