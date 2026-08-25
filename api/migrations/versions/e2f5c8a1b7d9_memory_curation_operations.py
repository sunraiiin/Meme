"""memory curator execution audit and undo records

Revision ID: e2f5c8a1b7d9
Revises: c8a4f1d2e3b4
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e2f5c8a1b7d9"
down_revision: Union[str, None] = "c8a4f1d2e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_curation_operations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("operation_kind", sa.String(length=64), nullable=False),
        sa.Column("risk", sa.String(length=16), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="confirmed"),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "operation_id", name="uq_memory_curation_user_operation"),
    )
    op.create_index(
        op.f("ix_memory_curation_operations_user_id"),
        "memory_curation_operations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_curation_operations_plan_id"),
        "memory_curation_operations",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_curation_operations_operation_id"),
        "memory_curation_operations",
        ["operation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_curation_operations_operation_kind"),
        "memory_curation_operations",
        ["operation_kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_curation_operations_status"),
        "memory_curation_operations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_curation_operations_created_at"),
        "memory_curation_operations",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_memory_curation_operations_created_at"), table_name="memory_curation_operations")
    op.drop_index(op.f("ix_memory_curation_operations_status"), table_name="memory_curation_operations")
    op.drop_index(op.f("ix_memory_curation_operations_operation_kind"), table_name="memory_curation_operations")
    op.drop_index(op.f("ix_memory_curation_operations_operation_id"), table_name="memory_curation_operations")
    op.drop_index(op.f("ix_memory_curation_operations_plan_id"), table_name="memory_curation_operations")
    op.drop_index(op.f("ix_memory_curation_operations_user_id"), table_name="memory_curation_operations")
    op.drop_table("memory_curation_operations")
