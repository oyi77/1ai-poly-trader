"""
Add data_quality_flags to trades

Revision ID: 20260422_backfill_data_quality_flags
Revises: 20260421_error_logging
Create Date: 2026-04-22 10:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260422_backfill_data_quality_flags'
down_revision = '20260315_task2_add_outcome_tables'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('trades', sa.Column(
        'data_quality_flags',
        sa.Text(),
        nullable=True
    ))

def downgrade():
    op.drop_column('trades', 'data_quality_flags')