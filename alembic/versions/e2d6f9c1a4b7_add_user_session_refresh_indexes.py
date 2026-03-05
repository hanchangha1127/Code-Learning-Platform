"""add user_session refresh token lookup indexes

Revision ID: e2d6f9c1a4b7
Revises: d7a6c9b14e2f
Create Date: 2026-02-10 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e2d6f9c1a4b7"
down_revision: Union[str, Sequence[str], None] = "d7a6c9b14e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {idx.get("name") for idx in inspector.get_indexes("user_sessions")}

    if "ix_user_sessions_refresh_token_hash" not in existing:
        op.create_index(
            "ix_user_sessions_refresh_token_hash",
            "user_sessions",
            ["refresh_token_hash"],
            unique=False,
        )

    if "ix_user_sessions_active_lookup" not in existing:
        op.create_index(
            "ix_user_sessions_active_lookup",
            "user_sessions",
            ["refresh_token_hash", "revoked_at", "expires_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_active_lookup", table_name="user_sessions")
    op.drop_index("ix_user_sessions_refresh_token_hash", table_name="user_sessions")
