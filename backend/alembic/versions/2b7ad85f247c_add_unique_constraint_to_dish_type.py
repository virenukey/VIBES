"""add unique constraint to dish type

Revision ID: 2b7ad85f247c
Revises: 62c982160665
Create Date: 2026-03-31 06:25:38.929566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b7ad85f247c'
down_revision: Union[str, Sequence[str], None] = '62c982160665'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_dish_types_name", table_name="dish_types")  # ← add this
    op.create_unique_constraint("uq_dish_types_name_tenant", "dish_types", ["name", "tenant_id"])



def downgrade() -> None:
    op.drop_constraint("uq_dish_types_name_tenant", "dish_types", type_="unique")
    op.create_index("ix_dish_types_name", "dish_types", ["name"], unique=True)  # ← add this