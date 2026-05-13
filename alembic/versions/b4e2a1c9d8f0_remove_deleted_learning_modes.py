"""remove deleted learning modes from problem_kind enum

Revision ID: b4e2a1c9d8f0
Revises: c8d9e1f2a3b4
Create Date: 2026-05-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b4e2a1c9d8f0"
down_revision: Union[str, Sequence[str], None] = "c8d9e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REMOVED_PROBLEM_KINDS = "'coding','code_calc','code_error','context_inference'"


def upgrade() -> None:
    op.execute(
        f"""
        DELETE rqi FROM review_queue_items rqi
        LEFT JOIN submissions s ON s.id = rqi.submission_id
        LEFT JOIN problems problem_ref ON problem_ref.id = rqi.problem_id
        LEFT JOIN problems submission_problem ON submission_problem.id = s.problem_id
        WHERE rqi.mode IN ('code-calc','code-error','context-inference')
           OR rqi.source_problem_id LIKE 'ccalc:%'
           OR rqi.source_problem_id LIKE 'cerr:%'
           OR rqi.source_problem_id LIKE 'cinfer:%'
           OR problem_ref.kind IN ({REMOVED_PROBLEM_KINDS})
           OR submission_problem.kind IN ({REMOVED_PROBLEM_KINDS})
        """
    )
    op.execute(
        """
        DELETE FROM platform_ops_events
        WHERE mode IN ('code-calc','code-error','context-inference')
        """
    )
    op.execute(
        f"""
        DELETE analyses FROM ai_analyses analyses
        JOIN submissions s ON s.id = analyses.submission_id
        JOIN problems p ON p.id = s.problem_id
        WHERE p.kind IN ({REMOVED_PROBLEM_KINDS})
        """
    )
    op.execute(
        f"""
        DELETE s FROM submissions s
        JOIN problems p ON p.id = s.problem_id
        WHERE p.kind IN ({REMOVED_PROBLEM_KINDS})
        """
    )
    op.execute(
        f"""
        DELETE stats FROM user_problem_stats stats
        JOIN problems p ON p.id = stats.problem_id
        WHERE p.kind IN ({REMOVED_PROBLEM_KINDS})
        """
    )
    op.execute(
        f"""
        DELETE FROM problems
        WHERE kind IN ({REMOVED_PROBLEM_KINDS})
        """
    )
    op.execute(
        """
        ALTER TABLE problems
        MODIFY COLUMN kind
        ENUM(
            'analysis',
            'code_block',
            'code_arrange',
            'auditor',
            'refactoring_choice',
            'code_blame'
        )
        NOT NULL
        """
    )


def downgrade() -> None:
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
