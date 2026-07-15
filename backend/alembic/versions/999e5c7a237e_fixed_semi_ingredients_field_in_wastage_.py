"""fixed semi-ingredients field in wastage model

Revision ID: 999e5c7a237e
Revises: 372d3d0cf729
Create Date: 2026-05-06 15:17:43.167513

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '999e5c7a237e'
down_revision: Union[str, Sequence[str], None] = '372d3d0cf729'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old FK constraint first
    op.drop_constraint('wastage_management_semi_finished_product_id_fkey', 'wastage_management', type_='foreignkey')
    
    # Change UUID -> Integer using raw SQL (USING NULL is safe since column was never populated)
    op.execute("ALTER TABLE wastage_management ALTER COLUMN semi_finished_product_id TYPE INTEGER USING NULL")
    
    # Add new FK pointing to semi_finished_products
    op.create_foreign_key(
        'wastage_management_semi_finished_product_id_fkey',
        'wastage_management', 'semi_finished_products',
        ['semi_finished_product_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('wastage_management_semi_finished_product_id_fkey', 'wastage_management', type_='foreignkey')
    
    op.execute("ALTER TABLE wastage_management ALTER COLUMN semi_finished_product_id TYPE UUID USING NULL")
    
    op.create_foreign_key(
        'wastage_management_semi_finished_product_id_fkey',
        'wastage_management', 'pre_prepared_dish_preparation',
        ['semi_finished_product_id'], ['id'],
        ondelete='SET NULL'
    )