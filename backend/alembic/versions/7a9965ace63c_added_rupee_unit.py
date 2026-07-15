"""added rupee unit

Revision ID: 7a9965ace63c
Revises: d39d0e733292
Create Date: 2026-04-16 10:13:57.424467

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a9965ace63c'
down_revision: Union[str, Sequence[str], None] = 'd39d0e733292'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TYPE unittype ADD VALUE 'rupee'")

def downgrade():
    # PostgreSQL doesn't support removing enum values easily
    pass