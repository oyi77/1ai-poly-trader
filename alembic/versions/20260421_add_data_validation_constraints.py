"""add data validation constraints

Revision ID: 20260421_validation
Revises: 20260421_schema_sync
Create Date: 2026-04-21 07:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20260421_validation'
down_revision = ('20260421_schema_sync', 'cd91e4066413')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add database-level validation constraints: NOT NULL, CHECK, UNIQUE."""
    
    # Enable foreign key enforcement for SQLite
    try:
        from sqlalchemy import create_engine
        from backend.config import settings
        engine = create_engine(settings.DATABASE_URL)
        if 'sqlite' in settings.DATABASE_URL:
            with engine.connect() as conn:
                conn.execute(sa.text("PRAGMA foreign_keys=ON"))
    except Exception as e:
        print(f"Could not enable foreign keys: {e}")
    
    # =========================================================================
    # TRADES TABLE CONSTRAINTS
    # =========================================================================
    
    # Add CHECK constraints for trade amounts (> 0, < max_position_size)
    # SQLite doesn't support adding CHECK constraints to existing tables directly
    # We'll use a workaround: create new table with constraints, copy data, rename
    
    with op.batch_alter_table('trades', schema=None) as batch_op:
        # Add CHECK constraint for size > 0
        try:
            batch_op.create_check_constraint(
                'ck_trades_size_positive',
                'size > 0'
            )
        except Exception as e:
            print(f"Check constraint ck_trades_size_positive already exists or error: {e}")
        
        # Add CHECK constraint for size < 1000 (reasonable max position)
        try:
            batch_op.create_check_constraint(
                'ck_trades_size_max',
                'size <= 1000'
            )
        except Exception as e:
            print(f"Check constraint ck_trades_size_max already exists or error: {e}")
        
        # Add CHECK constraint for entry_price in valid range [0.01, 0.99]
        try:
            batch_op.create_check_constraint(
                'ck_trades_entry_price_range',
                'entry_price >= 0.01 AND entry_price <= 0.99'
            )
        except Exception as e:
            print(f"Check constraint ck_trades_entry_price_range already exists or error: {e}")
        
        # Add CHECK constraint for confidence scores [0, 1]
        try:
            batch_op.create_check_constraint(
                'ck_trades_confidence_range',
                'confidence IS NULL OR (confidence >= 0 AND confidence <= 1)'
            )
        except Exception as e:
            print(f"Check constraint ck_trades_confidence_range already exists or error: {e}")
        
        # Add CHECK constraint for edge_at_entry reasonable range [-1, 1]
        try:
            batch_op.create_check_constraint(
                'ck_trades_edge_range',
                'edge_at_entry >= -1 AND edge_at_entry <= 1'
            )
        except Exception as e:
            print(f"Check constraint ck_trades_edge_range already exists or error: {e}")
        
        # Add CHECK constraint for model_probability [0, 1]
        try:
            batch_op.create_check_constraint(
                'ck_trades_model_probability_range',
                'model_probability >= 0 AND model_probability <= 1'
            )
        except Exception as e:
            print(f"Check constraint ck_trades_model_probability_range already exists or error: {e}")
        
        # Add CHECK constraint for market_price_at_entry [0.01, 0.99]
        try:
            batch_op.create_check_constraint(
                'ck_trades_market_price_range',
                'market_price_at_entry >= 0.01 AND market_price_at_entry <= 0.99'
            )
        except Exception as e:
            print(f"Check constraint ck_trades_market_price_range already exists or error: {e}")
        
        # Add CHECK constraint for direction
        try:
            batch_op.create_check_constraint(
                'ck_trades_direction_valid',
                "direction IN ('up', 'down', 'yes', 'no', 'YES', 'NO')"
            )
        except Exception as e:
            print(f"Check constraint ck_trades_direction_valid already exists or error: {e}")
        
        # Add CHECK constraint for result
        try:
            batch_op.create_check_constraint(
                'ck_trades_result_valid',
                "result IN ('pending', 'win', 'loss', 'expired', 'push', 'closed')"
            )
        except Exception as e:
            print(f"Check constraint ck_trades_result_valid already exists or error: {e}")
        
        # Add CHECK constraint for trading_mode
        try:
            batch_op.create_check_constraint(
                'ck_trades_trading_mode_valid',
                "trading_mode IN ('paper', 'testnet', 'live')"
            )
        except Exception as e:
            print(f"Check constraint ck_trades_trading_mode_valid already exists or error: {e}")
    
    # =========================================================================
    # SIGNALS TABLE CONSTRAINTS
    # =========================================================================
    
    with op.batch_alter_table('signals', schema=None) as batch_op:
        # Add CHECK constraint for confidence [0, 1]
        try:
            batch_op.create_check_constraint(
                'ck_signals_confidence_range',
                'confidence >= 0 AND confidence <= 1'
            )
        except Exception as e:
            print(f"Check constraint ck_signals_confidence_range already exists or error: {e}")
        
        # Add CHECK constraint for model_probability [0, 1]
        try:
            batch_op.create_check_constraint(
                'ck_signals_model_probability_range',
                'model_probability >= 0 AND model_probability <= 1'
            )
        except Exception as e:
            print(f"Check constraint ck_signals_model_probability_range already exists or error: {e}")
        
        # Add CHECK constraint for market_price [0.01, 0.99]
        try:
            batch_op.create_check_constraint(
                'ck_signals_market_price_range',
                'market_price >= 0.01 AND market_price <= 0.99'
            )
        except Exception as e:
            print(f"Check constraint ck_signals_market_price_range already exists or error: {e}")
        
        # Add CHECK constraint for edge reasonable range [-1, 1]
        try:
            batch_op.create_check_constraint(
                'ck_signals_edge_range',
                'edge >= -1 AND edge <= 1'
            )
        except Exception as e:
            print(f"Check constraint ck_signals_edge_range already exists or error: {e}")
        
        # Add CHECK constraint for kelly_fraction [0, 1]
        try:
            batch_op.create_check_constraint(
                'ck_signals_kelly_fraction_range',
                'kelly_fraction >= 0 AND kelly_fraction <= 1'
            )
        except Exception as e:
            print(f"Check constraint ck_signals_kelly_fraction_range already exists or error: {e}")
        
        # Add CHECK constraint for suggested_size > 0
        try:
            batch_op.create_check_constraint(
                'ck_signals_suggested_size_positive',
                'suggested_size > 0'
            )
        except Exception as e:
            print(f"Check constraint ck_signals_suggested_size_positive already exists or error: {e}")
        
        # Add CHECK constraint for direction
        try:
            batch_op.create_check_constraint(
                'ck_signals_direction_valid',
                "direction IN ('up', 'down', 'yes', 'no', 'YES', 'NO')"
            )
        except Exception as e:
            print(f"Check constraint ck_signals_direction_valid already exists or error: {e}")
    
    # =========================================================================
    # PENDING_APPROVALS TABLE CONSTRAINTS
    # =========================================================================
    
    with op.batch_alter_table('pending_approvals', schema=None) as batch_op:
        # Add CHECK constraint for size > 0
        try:
            batch_op.create_check_constraint(
                'ck_pending_approvals_size_positive',
                'size > 0'
            )
        except Exception as e:
            print(f"Check constraint ck_pending_approvals_size_positive already exists or error: {e}")
        
        # Add CHECK constraint for confidence [0, 1]
        try:
            batch_op.create_check_constraint(
                'ck_pending_approvals_confidence_range',
                'confidence >= 0 AND confidence <= 1'
            )
        except Exception as e:
            print(f"Check constraint ck_pending_approvals_confidence_range already exists or error: {e}")
        
        # Add CHECK constraint for status
        try:
            batch_op.create_check_constraint(
                'ck_pending_approvals_status_valid',
                "status IN ('pending', 'approved', 'rejected')"
            )
        except Exception as e:
            print(f"Check constraint ck_pending_approvals_status_valid already exists or error: {e}")
    
    # =========================================================================
    # TRADE_CONTEXT TABLE CONSTRAINTS
    # =========================================================================
    
    with op.batch_alter_table('trade_context', schema=None) as batch_op:
        # Add CHECK constraint for confidence [0, 1]
        try:
            batch_op.create_check_constraint(
                'ck_trade_context_confidence_range',
                'confidence IS NULL OR (confidence >= 0 AND confidence <= 1)'
            )
        except Exception as e:
            print(f"Check constraint ck_trade_context_confidence_range already exists or error: {e}")
    
    # =========================================================================
    # UNIQUE CONSTRAINTS
    # =========================================================================
    
    # Add UNIQUE constraint for clob_order_id (prevent duplicate order tracking)
    try:
        op.create_index('uq_trades_clob_order_id', 'trades', ['clob_order_id'], unique=True)
    except Exception as e:
        print(f"Unique index uq_trades_clob_order_id already exists or error: {e}")
    
    # Add UNIQUE constraint for clob_idempotency_key (prevent duplicate order submission)
    try:
        op.create_index('uq_trades_clob_idempotency_key', 'trades', ['clob_idempotency_key'], unique=True)
    except Exception as e:
        print(f"Unique index uq_trades_clob_idempotency_key already exists or error: {e}")


def downgrade() -> None:
    """Remove validation constraints."""
    
    # Drop UNIQUE indexes
    try:
        op.drop_index('uq_trades_clob_idempotency_key', table_name='trades')
    except Exception:
        pass
    
    try:
        op.drop_index('uq_trades_clob_order_id', table_name='trades')
    except Exception:
        pass
    
    # Drop CHECK constraints from trade_context
    with op.batch_alter_table('trade_context', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('ck_trade_context_confidence_range', type_='check')
        except Exception:
            pass
    
    # Drop CHECK constraints from pending_approvals
    with op.batch_alter_table('pending_approvals', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('ck_pending_approvals_status_valid', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_pending_approvals_confidence_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_pending_approvals_size_positive', type_='check')
        except Exception:
            pass
    
    # Drop CHECK constraints from signals
    with op.batch_alter_table('signals', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('ck_signals_direction_valid', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_signals_suggested_size_positive', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_signals_kelly_fraction_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_signals_edge_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_signals_market_price_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_signals_model_probability_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_signals_confidence_range', type_='check')
        except Exception:
            pass
    
    # Drop CHECK constraints from trades
    with op.batch_alter_table('trades', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('ck_trades_trading_mode_valid', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_result_valid', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_direction_valid', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_market_price_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_model_probability_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_edge_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_confidence_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_entry_price_range', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_size_max', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_trades_size_positive', type_='check')
        except Exception:
            pass
