"""added cm 

Revision ID: d39d0e733292
Revises: 2194b8bf617b
Create Date: 2026-04-14 06:28:27.151642

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd39d0e733292'
down_revision: Union[str, Sequence[str], None] = '2194b8bf617b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TYPE unittype ADD VALUE 'cm'")

def downgrade():
    # PostgreSQL doesn't support removing enum values easily
    pass