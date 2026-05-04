"""
Data cleanup before adding FK/CHECK constraints

Fixes orphaned strategy references and normalizes enum values
identified by validate_schema_constraints.py audit.

Revision ID: 20260504_data_cleanup_for_constraints
Revises: 20260422_backfill_data_quality_flags
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa

revision = '20260504_data_cleanup_for_constraints'
down_revision = '20260422_backfill_data_quality_flags'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    for strategy_name in ['weather', 'watchdog', 'unknown']:
        conn.execute(sa.text(
            "INSERT OR IGNORE INTO strategy_config "
            "(strategy_name, enabled, interval_seconds, params) "
            "VALUES (:name, 0, 3600, '{}')"
        ), {"name": strategy_name})

    conn.execute(sa.text(
        "UPDATE experiment_records SET strategy_name = NULL "
        "WHERE strategy_name = 'unknown'"
    ))


def downgrade() -> None:
    pass
