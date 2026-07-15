"""add_consumption_to_transactiontype_enum

Revision ID: 903123095a06
Revises: 0b2ab3ebe20d
Create Date: 2026-04-08 09:06:12.366591

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '903123095a06'
down_revision: Union[str, Sequence[str], None] = '0b2ab3ebe20d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("COMMIT")
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'consumption'")

def downgrade():
    pass
