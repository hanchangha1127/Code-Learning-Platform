"""add auditor to problem_kind enum

Revision ID: 4f1d5e9b2c31
Revises: e2d6f9c1a4b7
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4f1d5e9b2c31"
down_revision: Union[str, Sequence[str], None] = "e2d6f9c1a4b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block','auditor')
        NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block')
        NOT NULL
        """
    )
