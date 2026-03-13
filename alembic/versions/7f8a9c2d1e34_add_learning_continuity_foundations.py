"""add learning continuity and product ops foundations

Revision ID: 7f8a9c2d1e34
Revises: e6f4b7a9c812
Create Date: 2026-03-07 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f8a9c2d1e34"
down_revision: Union[str, Sequence[str], None] = "e6f4b7a9c812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_learning_goals (
            user_id BIGINT NOT NULL,
            weekly_target_sessions INT NOT NULL DEFAULT 12,
            focus_modes JSON NULL,
            focus_topics JSON NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (user_id),
            CONSTRAINT fk_user_learning_goals_user
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        ALTER TABLE problems
        ADD COLUMN prompt_version VARCHAR(80) NULL,
        ADD COLUMN content_status ENUM('pending','approved','hidden') NOT NULL DEFAULT 'pending',
        ADD COLUMN is_curated_sample BOOLEAN NOT NULL DEFAULT 0
        """
    )

    op.execute(
        """
        CREATE TABLE review_queue_items (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id BIGINT NOT NULL,
            problem_id BIGINT NULL,
            submission_id BIGINT NULL,
            source_problem_id VARCHAR(128) NULL,
            mode VARCHAR(50) NOT NULL,
            title VARCHAR(200) NOT NULL,
            weakness_tag VARCHAR(80) NULL,
            due_at DATETIME NOT NULL,
            priority INT NOT NULL DEFAULT 50,
            status ENUM('pending','completed','dismissed') NOT NULL DEFAULT 'pending',
            completed_at DATETIME NULL,
            payload JSON NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_review_queue_user
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT fk_review_queue_problem
                FOREIGN KEY (problem_id) REFERENCES problems (id) ON DELETE SET NULL,
            CONSTRAINT fk_review_queue_submission
                FOREIGN KEY (submission_id) REFERENCES submissions (id) ON DELETE SET NULL
        )
        """
    )
    op.create_index("ix_review_queue_user_due", "review_queue_items", ["user_id", "status", "due_at"], unique=False)
    op.create_index("ix_review_queue_problem", "review_queue_items", ["problem_id", "status"], unique=False)

    op.execute(
        """
        CREATE TABLE platform_ops_events (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id BIGINT NULL,
            request_id VARCHAR(64) NULL,
            event_type VARCHAR(80) NOT NULL,
            mode VARCHAR(50) NULL,
            status VARCHAR(40) NULL,
            latency_ms INT NULL,
            payload JSON NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_platform_ops_events_user
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.create_index("ix_platform_ops_event_type_created", "platform_ops_events", ["event_type", "created_at"], unique=False)
    op.create_index("ix_platform_ops_request_id", "platform_ops_events", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_platform_ops_request_id", table_name="platform_ops_events")
    op.drop_index("ix_platform_ops_event_type_created", table_name="platform_ops_events")
    op.drop_table("platform_ops_events")

    op.drop_index("ix_review_queue_problem", table_name="review_queue_items")
    op.drop_index("ix_review_queue_user_due", table_name="review_queue_items")
    op.drop_table("review_queue_items")

    op.drop_column("problems", "is_curated_sample")
    op.drop_column("problems", "content_status")
    op.drop_column("problems", "prompt_version")

    op.drop_table("user_learning_goals")
