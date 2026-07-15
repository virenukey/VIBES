"""unique constraint fixed

Revision ID: 26bf20093292
Revises: 2b7ad85f247c
Create Date: 2026-03-31 08:26:53.356374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26bf20093292'
down_revision: Union[str, Sequence[str], None] = '2b7ad85f247c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass
   


def downgrade() -> None:
    """Downgrade schema."""
    pass
   