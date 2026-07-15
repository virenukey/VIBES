"""add enums of unittype

Revision ID: b2b36c0017b3
Revises: e057627c0c0f
Create Date: 2026-02-18 16:44:55.032725

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2b36c0017b3'
down_revision: Union[str, Sequence[str], None] = 'e057627c0c0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # PostgreSQL requires this exact syntax to add enum values
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'pcs'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'packet'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'box'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'carton'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'dozen'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'bundle'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'roll'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'sheet'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'sachet'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'bottle'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'can'")
    op.execute("ALTER TYPE unittype ADD VALUE IF NOT EXISTS 'bag'")

def downgrade():
    # PostgreSQL does NOT support removing enum values directly
    # You have to recreate the type if you want to rollback
    op.execute("""
        ALTER TYPE unittype RENAME TO unittype_old;
        
        CREATE TYPE unittype AS ENUM (
            'kg', 'gm', 'mg', 'liter', 'ml'
        );
        
        ALTER TABLE inventory 
            ALTER COLUMN unit TYPE unittype 
            USING unit::text::unittype;
            
        ALTER TABLE inventory 
            ALTER COLUMN purchase_unit TYPE unittype 
            USING purchase_unit::text::unittype;
        
        DROP TYPE unittype_old;
    """)