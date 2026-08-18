"""remove notification backend and scheduled-task notification flag

Revision ID: c8a4f1d2e3b4
Revises: 6727223d45f9
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8a4f1d2e3b4"
down_revision: Union[str, None] = "6727223d45f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("agent_tasks", "notify_enabled")
    op.drop_index("ix_notify_channels_user_id", table_name="notify_channels")
    op.drop_index("ix_notify_channels_enabled", table_name="notify_channels")
    op.drop_table("notify_channels")


def downgrade() -> None:
    op.create_table(
        "notify_channels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("channel_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("target_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notify_channels_enabled", "notify_channels", ["enabled"], unique=False)
    op.create_index("ix_notify_channels_user_id", "notify_channels", ["user_id"], unique=False)
    op.add_column("agent_tasks", sa.Column("notify_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
