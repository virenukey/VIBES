"""added combo enum in wastagetype

Revision ID: 944768c381cb
Revises: d8fb1dcc7a14
Create Date: 2026-05-23 06:21:19.871488

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '944768c381cb'
down_revision: Union[str, Sequence[str], None] = 'd8fb1dcc7a14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE wastagetype ADD VALUE 'combo'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
