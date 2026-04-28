"""
Add outcome-related tables: strategy_outcomes, param_changes, strategy_health, trading_calibration_records

Revision ID: 20260315_task2_add_outcome_tables
Revises: 882388989398_phase2_feature_schemas
Create Date: 2026-03-15

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260315_task2_add_outcome_tables'
down_revision = '20260421_validation'
branch_labels = None
depends_on = None

def upgrade():
    # Create strategy_outcomes table
    op.create_table(
        'strategy_outcomes',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('strategy', sa.String, nullable=False),
        sa.Column('market_ticker', sa.String, nullable=False),
        sa.Column('market_type', sa.String, nullable=False),
        sa.Column('trading_mode', sa.String, nullable=False),
        sa.Column('direction', sa.String, nullable=False),
        sa.Column('model_probability', sa.Float, nullable=True),
        sa.Column('market_price', sa.Float, nullable=True),
        sa.Column('edge_at_entry', sa.Float, nullable=True),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('result', sa.String, nullable=True),  # Enum-like values: win/loss/push
        sa.Column('pnl', sa.Float, nullable=True),
        sa.Column('reward', sa.Float, nullable=True),  # Sharpe-adjusted reward
        sa.Column('settled_at', sa.DateTime, nullable=True),
        sa.Column('trade_id', sa.Integer, sa.ForeignKey('trades.id'), nullable=False)
    )

    # Create param_changes table
    op.create_table(
        'param_changes',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('strategy', sa.String, nullable=False),
        sa.Column('param_name', sa.String, nullable=False),
        sa.Column('old_value', sa.Float, nullable=True),
        sa.Column('new_value', sa.Float, nullable=True),
        sa.Column('change_pct', sa.Float, nullable=True),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('reasoning', sa.Text, nullable=True),
        sa.Column('applied_at', sa.DateTime, nullable=False),
        sa.Column('reverted_at', sa.DateTime, nullable=True),
        sa.Column('pre_change_sharpe', sa.Float, nullable=True),
        sa.Column('post_change_sharpe', sa.Float, nullable=True),
        sa.Column('auto_applied', sa.Boolean, nullable=False, default=False)
    )

    # Create strategy_health table
    op.create_table(
        'strategy_health',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('strategy', sa.String, nullable=False),
        sa.Column('total_trades', sa.Integer, nullable=False),
        sa.Column('wins', sa.Integer, nullable=False),
        sa.Column('losses', sa.Integer, nullable=False),
        sa.Column('win_rate', sa.Float, nullable=False),
        sa.Column('sharpe', sa.Float, nullable=False),
        sa.Column('max_drawdown', sa.Float, nullable=True),
        sa.Column('brier_score', sa.Float, nullable=True),
        sa.Column('psi_score', sa.Float, nullable=True),
        sa.Column('status', sa.String, nullable=False),  # Enum-like: active/warned/paused/killed
        sa.Column('last_updated', sa.DateTime, nullable=False)
    )

    # Create trading_calibration_records table
    op.create_table(
        'trading_calibration_records',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('strategy', sa.String, nullable=False),
        sa.Column('predicted_prob', sa.Float, nullable=False),
        sa.Column('actual_outcome', sa.Integer, nullable=False),  # 0/1
        sa.Column('brier_score', sa.Float, nullable=True),
        sa.Column('market_type', sa.String, nullable=False),
        sa.Column('timestamp', sa.DateTime, nullable=False)
    )

    # Add indexes for query performance
    op.create_index('ix_strategy_outcomes_strategy', 'strategy_outcomes', ['strategy'])
    op.create_index('ix_strategy_outcomes_strategy_market_type', 'strategy_outcomes', ['strategy', 'market_type'])
    op.create_index('ix_strategy_outcomes_settled_at', 'strategy_outcomes', ['settled_at'])

def downgrade():
    # Drop indexes first before removing tables
    op.drop_index('ix_strategy_outcomes_strategy', table_name='strategy_outcomes')
    op.drop_index('ix_strategy_outcomes_strategy_market_type', table_name='strategy_outcomes')
    op.drop_index('ix_strategy_outcomes_settled_at', table_name='strategy_outcomes')

    # Drop all created tables
    op.drop_table('strategy_outcomes')
    op.drop_table('param_changes')
    op.drop_table('strategy_health')
    op.drop_table('trading_calibration_records')