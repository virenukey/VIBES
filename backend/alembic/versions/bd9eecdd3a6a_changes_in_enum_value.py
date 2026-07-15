"""changes in enum value

Revision ID: bd9eecdd3a6a
Revises: 2ce154bf949e
Create Date: 2026-02-23 10:13:56.882323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd9eecdd3a6a'
down_revision: Union[str, Sequence[str], None] = '2ce154bf949e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── Fix wastagetype ──────────────────────────────────
    op.execute("ALTER TYPE wastagetype RENAME TO wastagetype_old")

    op.execute("""
        CREATE TYPE wastagetype AS ENUM (
            'dish', 
            'inventory', 
            'semi_finished'
        )
    """)

    op.execute("""
        ALTER TABLE wastage_management 
        ALTER COLUMN wastage_type TYPE wastagetype 
        USING LOWER(wastage_type::text)::wastagetype
    """)

    op.execute("DROP TYPE wastagetype_old")

    # ── Fix wastagereason ────────────────────────────────
    op.execute("ALTER TYPE wastagereason RENAME TO wastagereason_old")

    op.execute("""
        CREATE TYPE wastagereason AS ENUM (
            'expiry',
            'damage',
            'contamination',
            'unsold_dish',
            'preparation_error',
            'spillage',
            'staff_meal',
            'sampling',
            'other'
        )
    """)

    op.execute("""
        ALTER TABLE wastage_management 
        ALTER COLUMN wastage_reason TYPE wastagereason 
        USING LOWER(wastage_reason::text)::wastagereason
    """)

    op.execute("DROP TYPE wastagereason_old")


def downgrade() -> None:

    # ── Revert wastagetype ───────────────────────────────
    op.execute("ALTER TYPE wastagetype RENAME TO wastagetype_old")

    op.execute("""
        CREATE TYPE wastagetype AS ENUM (
            'DISH', 
            'INVENTORY'
        )
    """)

    op.execute("""
        ALTER TABLE wastage_management 
        ALTER COLUMN wastage_type TYPE wastagetype 
        USING UPPER(wastage_type::text)::wastagetype
    """)

    op.execute("DROP TYPE wastagetype_old")

    # ── Revert wastagereason ─────────────────────────────
    op.execute("ALTER TYPE wastagereason RENAME TO wastagereason_old")

    op.execute("""
        CREATE TYPE wastagereason AS ENUM (
            'EXPIRY', 'DAMAGE', 'CONTAMINATION',
            'UNSOLD_DISH', 'PREPARATION_ERROR',
            'SPILLAGE', 'STAFF_MEAL', 'SAMPLING', 'OTHER'
        )
    """)

    op.execute("""
        ALTER TABLE wastage_management 
        ALTER COLUMN wastage_reason TYPE wastagereason 
        USING UPPER(wastage_reason::text)::wastagereason
    """)

    op.execute("DROP TYPE wastagereason_old")