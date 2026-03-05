"""add context_inference to problem_kind enum

Revision ID: 9c2a7f54b3de
Revises: 4f1d5e9b2c31
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c2a7f54b3de"
down_revision: Union[str, Sequence[str], None] = "4f1d5e9b2c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block','auditor','context_inference')
        NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM('coding','code_block','auditor')
        NOT NULL
        """
    )
