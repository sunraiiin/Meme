"""align memory curation audit timestamps with ORM nullability

Revision ID: f3a7c9d1e5b2
Revises: e2f5c8a1b7d9
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f3a7c9d1e5b2"
down_revision: Union[str, None] = "e2f5c8a1b7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "memory_curation_operations",
        "confirmed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "memory_curation_operations",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "memory_curation_operations",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "memory_curation_operations",
        "confirmed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
