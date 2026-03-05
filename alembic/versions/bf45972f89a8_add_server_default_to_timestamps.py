"""add server default to timestamps

Revision ID: bf45972f89a8
Revises: f809335d6261
Create Date: 2026-01-31 16:53:30.235139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf45972f89a8'
down_revision: Union[str, Sequence[str], None] = 'f809335d6261'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # problems
    op.alter_column(
        "problems",
        "created_at",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "problems",
        "updated_at",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )

    # users (TimestampMixin 쓰는 테이블들 전부)
    op.alter_column(
        "users",
        "created_at",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "updated_at",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column("problems", "created_at", server_default=None)
    op.alter_column("problems", "updated_at", server_default=None)
    op.alter_column("users", "created_at", server_default=None)
    op.alter_column("users", "updated_at", server_default=None)
