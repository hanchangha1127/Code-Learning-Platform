"""add processing to submission status enum

Revision ID: bcebd7111fc8
Revises: bf45972f89a8
Create Date: 2026-02-06 14:04:22.281520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcebd7111fc8'
down_revision: Union[str, Sequence[str], None] = 'bf45972f89a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE submissions
        MODIFY COLUMN status
        ENUM('pending','processing','passed','failed','error')
        NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE submissions
        MODIFY COLUMN status
        ENUM('pending','passed','failed','error')
        NOT NULL
        """
    )
