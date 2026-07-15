"""fix_transactiontype_enum_to_uppercase

Revision ID: 70127105b66d
Revises: 903123095a06
Create Date: 2026-04-08 09:14:01.110675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70127105b66d'
down_revision: Union[str, Sequence[str], None] = '903123095a06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("COMMIT")
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'CONSUMPTION'")

def downgrade():
    pass
