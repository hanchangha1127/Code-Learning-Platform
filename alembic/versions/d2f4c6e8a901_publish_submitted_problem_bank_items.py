"""publish submitted problems for the public problem bank

Revision ID: d2f4c6e8a901
Revises: b4e2a1c9d8f0
Create Date: 2026-05-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d2f4c6e8a901"
down_revision: Union[str, Sequence[str], None] = "b4e2a1c9d8f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTIVE_PROBLEM_KINDS = (
    "'analysis',"
    "'code_block',"
    "'code_arrange',"
    "'auditor',"
    "'refactoring_choice',"
    "'code_blame'"
)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE problems p
        JOIN (
            SELECT DISTINCT problem_id
            FROM submissions
            WHERE problem_id IS NOT NULL
        ) submitted ON submitted.problem_id = p.id
        SET p.is_published = 1
        WHERE p.content_status <> 'hidden'
          AND p.answer_payload IS NOT NULL
          AND p.kind IN ({ACTIVE_PROBLEM_KINDS})
        """
    )


def downgrade() -> None:
    # Publication can be user-visible state, so do not automatically hide rows
    # when rolling back this migration.
    pass
