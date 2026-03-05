"""add refactoring_choice to problem_kind enum

Revision ID: a1f5d8e7c9ab
Revises: 9c2a7f54b3de
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1f5d8e7c9ab"
down_revision: Union[str, Sequence[str], None] = "9c2a7f54b3de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block','auditor','context_inference','refactoring_choice')
        NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block','auditor','context_inference')
        NOT NULL
        """
    )
