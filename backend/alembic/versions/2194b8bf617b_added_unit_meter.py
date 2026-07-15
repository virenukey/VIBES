"""added unit meter

Revision ID: 2194b8bf617b
Revises: 70127105b66d
Create Date: 2026-04-13 15:28:38.008357

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2194b8bf617b'
down_revision: Union[str, Sequence[str], None] = '70127105b66d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# In your alembic migration file
def upgrade():
    op.execute("ALTER TYPE unittype ADD VALUE 'm'")
    op.execute("ALTER TYPE unittype ADD VALUE 'mm'")

def downgrade():
    # PostgreSQL doesn't support removing enum values easily
    pass