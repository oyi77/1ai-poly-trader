"""add_fee_and_slippage_to_trades

Revision ID: 68beef868df4
Revises: 51c2bc15c671
Create Date: 2026-04-19 01:37:01.486557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68beef868df4'
down_revision: Union[str, Sequence[str], None] = '51c2bc15c671'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fee and slippage columns to trades table."""
    # Add fee column (nullable Decimal for transaction fees)
    op.add_column('trades', sa.Column('fee', sa.Numeric(precision=10, scale=2), nullable=True))
    
    # Add slippage column (nullable Decimal for price slippage analysis)
    op.add_column('trades', sa.Column('slippage', sa.Numeric(precision=10, scale=6), nullable=True))


def downgrade() -> None:
    """Remove fee and slippage columns from trades table."""
    op.drop_column('trades', 'slippage')
    op.drop_column('trades', 'fee')
