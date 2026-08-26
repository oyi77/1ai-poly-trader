"""create meteora DLMM tables

Revision ID: create_meteora_tables
Revises: arb_exec_status_001
Create Date: 2026-08-25

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "create_meteora_tables"
down_revision: Union[str, Sequence[str], None] = "arb_exec_status_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dt() -> sa.types.TypeEngine:
    return sa.DateTime()


def upgrade() -> None:
    op.create_table(
        "meteora_pool_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.String(), nullable=True),
        sa.Column("pool_address", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("active_tvl", sa.Float(), nullable=True),
        sa.Column("fee_active_tvl_ratio", sa.Float(), nullable=True),
        sa.Column("volume_active_tvl_ratio", sa.Float(), nullable=True),
        sa.Column("unique_lps", sa.Float(), nullable=True),
        sa.Column("positions_created", sa.Float(), nullable=True),
        sa.Column("volatility", sa.Float(), nullable=True),
        sa.Column("base_token_holders", sa.Integer(), nullable=True),
        sa.Column("organic_score", sa.Float(), nullable=True),
        sa.Column("quote_organic_score", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("launchpad", sa.String(), nullable=True),
        sa.Column("bin_step", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("captured_at", _dt(), nullable=True),
    )
    op.create_index("ix_meteora_pool_snapshots_id", "meteora_pool_snapshots", ["id"])
    op.create_index("ix_meteora_pool_snapshots_cycle_id", "meteora_pool_snapshots", ["cycle_id"])
    op.create_index(
        "ix_meteora_pool_snapshots_pool_address",
        "meteora_pool_snapshots",
        ["pool_address"],
    )
    op.create_index(
        "ix_meteora_pool_snapshots_captured_at",
        "meteora_pool_snapshots",
        ["captured_at"],
    )

    op.create_table(
        "meteora_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.String(), nullable=True),
        sa.Column("pool_address", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("degen_score", sa.Float(), nullable=True),
        sa.Column("weighted_score", sa.Float(), nullable=True),
        sa.Column("sub_trading", sa.Float(), nullable=True),
        sa.Column("sub_lp", sa.Float(), nullable=True),
        sa.Column("sub_fees", sa.Float(), nullable=True),
        sa.Column("sub_liquidity", sa.Float(), nullable=True),
        sa.Column("rejected", sa.Boolean(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("signal_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", _dt(), nullable=True),
    )
    op.create_index("ix_meteora_candidates_id", "meteora_candidates", ["id"])
    op.create_index("ix_meteora_candidates_cycle_id", "meteora_candidates", ["cycle_id"])
    op.create_index("ix_meteora_candidates_pool_address", "meteora_candidates", ["pool_address"])
    op.create_index("ix_meteora_candidates_degen_score", "meteora_candidates", ["degen_score"])
    op.create_index("ix_meteora_candidates_rejected", "meteora_candidates", ["rejected"])
    op.create_index("ix_meteora_candidates_created_at", "meteora_candidates", ["created_at"])

    op.create_table(
        "meteora_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mode", sa.String(), nullable=True),
        sa.Column("strategy", sa.String(), nullable=True),
        sa.Column("pool_address", sa.String(), nullable=True),
        sa.Column("pool_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("side", sa.String(), nullable=True),
        sa.Column("bins_below", sa.Integer(), nullable=True),
        sa.Column("bins_above", sa.Integer(), nullable=True),
        sa.Column("bin_step", sa.Float(), nullable=True),
        sa.Column("lower_price", sa.Float(), nullable=True),
        sa.Column("upper_price", sa.Float(), nullable=True),
        sa.Column("amount_sol", sa.Float(), nullable=True),
        sa.Column("initial_value_usd", sa.Float(), nullable=True),
        sa.Column("signal_snapshot", sa.JSON(), nullable=True),
        sa.Column("entry_cycle_id", sa.String(), nullable=True),
        sa.Column("onchain_position_mint", sa.String(), nullable=True),
        sa.Column("tx_signature_open", sa.String(), nullable=True),
        sa.Column("tx_signature_close", sa.String(), nullable=True),
        sa.Column("fees_earned_usd", sa.Float(), nullable=True),
        sa.Column("final_value_usd", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("minutes_in_range", sa.Integer(), nullable=True),
        sa.Column("minutes_held", sa.Integer(), nullable=True),
        sa.Column("oor_event_count", sa.Integer(), nullable=True),
        sa.Column("max_adverse_excursion_pct", sa.Float(), nullable=True),
        sa.Column("close_reason", sa.String(), nullable=True),
        sa.Column("opened_at", _dt(), nullable=True),
        sa.Column("closed_at", _dt(), nullable=True),
    )
    op.create_index("ix_meteora_positions_id", "meteora_positions", ["id"])
    op.create_index(
        "ix_meteora_positions_pool_address", "meteora_positions", ["pool_address"]
    )
    op.create_index(
        "ix_meteora_positions_status", "meteora_positions", ["status", "mode"]
    )
    op.create_index("ix_meteora_positions_opened_at", "meteora_positions", ["opened_at"])
    op.create_index("ix_meteora_positions_closed_at", "meteora_positions", ["closed_at"])

    op.create_table(
        "meteora_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("pool_address", sa.String(), nullable=True),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("risks", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("alternatives_considered", sa.JSON(), nullable=True),
        sa.Column("created_at", _dt(), nullable=True),
    )
    op.create_index("ix_meteora_decisions_id", "meteora_decisions", ["id"])
    op.create_index("ix_meteora_decisions_action", "meteora_decisions", ["action"])
    op.create_index("ix_meteora_decisions_pool_address", "meteora_decisions", ["pool_address"])
    op.create_index("ix_meteora_decisions_position_id", "meteora_decisions", ["position_id"])
    op.create_index("ix_meteora_decisions_created_at", "meteora_decisions", ["created_at"])

    op.create_table(
        "meteora_lessons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("pool_address", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("perf_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", _dt(), nullable=True),
    )
    op.create_index("ix_meteora_lessons_id", "meteora_lessons", ["id"])
    op.create_index("ix_meteora_lessons_position_id", "meteora_lessons", ["position_id"])
    op.create_index("ix_meteora_lessons_pool_address", "meteora_lessons", ["pool_address"])
    op.create_index("ix_meteora_lessons_created_at", "meteora_lessons", ["created_at"])

    op.create_table(
        "meteora_signal_weights",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_name", sa.String(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("win_rate_with_signal", sa.Float(), nullable=True),
        sa.Column("win_rate_without_signal", sa.Float(), nullable=True),
        sa.Column("last_recalc_at", _dt(), nullable=True),
    )
    op.create_index("ix_meteora_signal_weights_id", "meteora_signal_weights", ["id"])
    op.create_index(
        "ix_meteora_signal_weights_signal_name",
        "meteora_signal_weights",
        ["signal_name"],
        unique=True,
    )

    op.create_table(
        "meteora_cooldowns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("target", sa.String(), nullable=True),
        sa.Column("trigger", sa.String(), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=True),
        sa.Column("expires_at", _dt(), nullable=True),
        sa.Column("created_at", _dt(), nullable=True),
    )
    op.create_index("ix_meteora_cooldowns_id", "meteora_cooldowns", ["id"])
    op.create_index("ix_meteora_cooldowns_scope", "meteora_cooldowns", ["scope"])
    op.create_index("ix_meteora_cooldowns_target", "meteora_cooldowns", ["target"])
    op.create_index("ix_meteora_cooldowns_expires_at", "meteora_cooldowns", ["expires_at"])


def downgrade() -> None:
    for table in (
        "meteora_cooldowns",
        "meteora_signal_weights",
        "meteora_lessons",
        "meteora_decisions",
        "meteora_positions",
        "meteora_candidates",
        "meteora_pool_snapshots",
    ):
        op.drop_table(table)
