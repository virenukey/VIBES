"""added is_active and dish_not_ordered enum in wastage model

Revision ID: 35687e7604c4
Revises: 5ba7d291ffe5
Create Date: 2026-05-15 07:10:20.357412
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '35687e7604c4'
down_revision: Union[str, Sequence[str], None] = '5ba7d291ffe5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_active column
    op.add_column('wastage_management', sa.Column('is_active', sa.Boolean(), nullable=True))

    # Add dish_not_ordered enum value for the first time
    op.execute("ALTER TYPE wastagereason ADD VALUE 'dish_not_ordered'")


def downgrade() -> None:
    # Undo: remove is_active column (only runs if you rollback)
    op.drop_column('wastage_management', 'is_active')

    # Note: PostgreSQL does not support DROP VALUE for enums
    # 'dish_not_ordered' cannot be removed without recreating the entire enum type