"""
Add FK constraints for strategy_name columns

Revision ID: 20260504_add_strategy_fk_constraints
Revises: 20260504_data_cleanup_for_constraints
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa

revision = '20260504_add_strategy_fk_constraints'
down_revision = '20260504_data_cleanup_for_constraints'
branch_labels = None
depends_on = None

FK_CONSTRAINTS = [
    ("trades", "strategy", "fk_trades_strategy", "SET NULL"),
    ("signals", "track_name", "fk_signals_track_name", "SET NULL"),
    ("decision_log", "strategy", "fk_decision_log_strategy", "CASCADE"),
    ("trade_attempts", "strategy", "fk_trade_attempts_strategy", "SET NULL"),
    ("strategy_outcomes", "strategy", "fk_strategy_outcomes_strategy", "CASCADE"),
    ("strategy_health", "strategy", "fk_strategy_health_strategy", "CASCADE"),
    ("param_changes", "strategy", "fk_param_changes_strategy", "CASCADE"),
    ("trading_calibration_records", "strategy", "fk_trading_cal_strategy", "CASCADE"),
    ("proposal_feedback", "strategy", "fk_proposal_feedback_strategy", "CASCADE"),
    ("evolution_lineage", "strategy_name", "fk_evolution_lineage_strategy", "CASCADE"),
    ("meta_learning", "strategy", "fk_meta_learning_strategy", "CASCADE"),
    ("blocked_signal_counterfactual", "strategy", "fk_blocked_signal_strategy", "CASCADE"),
    ("activity_log", "strategy_name", "fk_activity_log_strategy", "SET NULL"),
    ("strategy_proposal", "strategy_name", "fk_strategy_proposal_strategy", "CASCADE"),
    ("calibration_records", "strategy", "fk_calibration_records_strategy", "CASCADE"),
    ("strategy_performance_snapshots", "strategy", "fk_strat_perf_strategy", "CASCADE"),
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("PRAGMA foreign_keys=OFF"))

    for name in conn.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_alembic_tmp%'"
    )).scalars().all():
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{name}"'))

    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()

    for table, column, constraint_name, on_delete in FK_CONSTRAINTS:
        if table not in existing_tables:
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            try:
                batch_op.create_foreign_key(
                    constraint_name,
                    referent_table='strategy_config',
                    local_cols=[column],
                    remote_cols=['strategy_name'],
                    ondelete=on_delete,
                )
            except Exception as e:
                print(f"FK {constraint_name}: {e}")

    conn.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    for table, column, constraint_name, on_delete in reversed(FK_CONSTRAINTS):
        with op.batch_alter_table(table, schema=None) as batch_op:
            try:
                batch_op.drop_constraint(constraint_name, type_='foreignkey')
            except Exception as e:
                print(f"Drop FK {constraint_name}: {e}")
