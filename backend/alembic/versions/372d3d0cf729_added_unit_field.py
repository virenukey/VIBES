"""added unit field

Revision ID: 372d3d0cf729
Revises: e8e4d3a1ea6d
Create Date: 2026-04-27 10:54:57.663107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '372d3d0cf729'
down_revision: Union[str, Sequence[str], None] = 'e8e4d3a1ea6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'unit'")


def downgrade():
    # PostgreSQL doesn't support removing enum values directly
    pass