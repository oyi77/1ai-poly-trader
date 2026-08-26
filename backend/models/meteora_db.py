"""Domain model: Meteora DLMM liquidity provision.

Tables backing the Meteora LP subsystem:
- pool snapshots captured per screening cycle
- scored candidates surfaced by the screener
- paper/live LP positions with entry/exit telemetry
- decision log (deploy/close/skip with reasons + rejected alternatives)
- lessons derived from closed positions
- darwinian signal weights (recalculated from close history)
- pool/base-mint cooldowns after repeated failures

Split from database.py convention; re-exported there for backward compat.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from backend.models.engine import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MeteoraPoolSnapshot(Base):
    """Raw pool-discovery row captured during a screening cycle."""

    __tablename__ = "meteora_pool_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String, index=True)  # groups one screening run
    pool_address = Column(String, index=True)
    name = Column(String)

    # Scorer inputs (discovery API, timeframe-normalized upstream)
    active_tvl = Column(Float)
    fee_active_tvl_ratio = Column(Float)
    volume_active_tvl_ratio = Column(Float)
    unique_lps = Column(Float)
    positions_created = Column(Float)
    volatility = Column(Float)
    base_token_holders = Column(Integer)
    organic_score = Column(Float)  # nullable upstream
    quote_organic_score = Column(Float)
    market_cap = Column(Float)
    launchpad = Column(String, nullable=True)
    bin_step = Column(Float)  # from dlmm_params; nullable upstream

    # Raw payload for audit/reprocessing
    payload = Column(JSON)

    captured_at = Column(DateTime, default=_utcnow, index=True)


class MeteoraCandidate(Base):
    """A pool that passed hard filters and received a Degen score."""

    __tablename__ = "meteora_candidates"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String, index=True)
    pool_address = Column(String, index=True)
    name = Column(String)

    degen_score = Column(Float, index=True)
    weighted_score = Column(Float)  # degen × darwin-weighted signals
    sub_trading = Column(Float)
    sub_lp = Column(Float)
    sub_fees = Column(Float)
    sub_liquidity = Column(Float)

    rejected = Column(Boolean, default=False, index=True)
    reject_reason = Column(Text, nullable=True)

    signal_snapshot = Column(JSON)  # entry-time signal values for darwin correlation
    created_at = Column(DateTime, default=_utcnow, index=True)


class MeteoraPosition(Base):
    """An LP position opened by the paper or live agent."""

    __tablename__ = "meteora_positions"
    __table_args__ = (Index("ix_meteora_positions_status", "status", "mode"),)

    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String, default="paper")  # "paper" | "live" (composite ix below)
    strategy = Column(String, default="bid_ask")  # spot | bid_ask | curve
    pool_address = Column(String, index=True)
    pool_name = Column(String)

    status = Column(String, default="open")  # open | closed | error
    side = Column(String, default="two_sided")  # two_sided | bid | ask
    bins_below = Column(Integer, nullable=True)
    bins_above = Column(Integer, nullable=True)
    bin_step = Column(Float, nullable=True)
    lower_price = Column(Float)
    upper_price = Column(Float)
    amount_sol = Column(Float)
    initial_value_usd = Column(Float, nullable=True)

    # Entry-time context for learning loops
    signal_snapshot = Column(JSON)
    entry_cycle_id = Column(String, nullable=True)

    # Live-telemetry
    onchain_position_mint = Column(String, nullable=True)
    tx_signature_open = Column(String, nullable=True)
    tx_signature_close = Column(String, nullable=True)

    # Close-out metrics (paper + live)
    fees_earned_usd = Column(Float, default=0.0)
    final_value_usd = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)  # (final+fees)/initial - 1
    minutes_in_range = Column(Integer, default=0)
    minutes_held = Column(Integer, default=0)
    oor_event_count = Column(Integer, default=0)
    max_adverse_excursion_pct = Column(Float, nullable=True)
    close_reason = Column(
        String, nullable=True
    )  # oor|stop_loss|take_profit|trailing_tp|yield_floor|manual|kill_switch

    opened_at = Column(DateTime, default=_utcnow, index=True)
    closed_at = Column(DateTime, nullable=True, index=True)


class MeteoraDecision(Base):
    """Decision-log entry: every deploy/close/skip/no-deploy outcome."""

    __tablename__ = "meteora_decisions"

    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String)  # screener | manager | killswitch | manual
    action = Column(String, index=True)  # deploy | close | skip | no_deploy | reject
    pool_address = Column(String, nullable=True, index=True)
    position_id = Column(Integer, nullable=True, index=True)
    mode = Column(String, default="paper")

    summary = Column(Text)
    reason = Column(Text)
    risks = Column(JSON, nullable=True)  # list[str]
    metrics = Column(JSON, nullable=True)  # dict of key numbers at decision time
    alternatives_considered = Column(JSON, nullable=True)  # rejected options + why

    created_at = Column(DateTime, default=_utcnow, index=True)


class MeteoraLesson(Base):
    """Lesson derived after a notable good/bad position outcome."""

    __tablename__ = "meteora_lessons"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, nullable=True, index=True)
    pool_address = Column(String, nullable=True, index=True)
    kind = Column(String)  # positive | negative
    text = Column(Text)  # ≤400 chars sanitized lesson
    perf_snapshot = Column(JSON)  # full performance record at derivation time
    created_at = Column(DateTime, default=_utcnow, index=True)


class MeteoraSignalWeight(Base):
    """Darwinian weight per screening signal; recalculated from close history."""

    __tablename__ = "meteora_signal_weights"

    id = Column(Integer, primary_key=True, index=True)
    signal_name = Column(String, unique=True, index=True)
    weight = Column(Float, default=1.0)
    sample_count = Column(Integer, default=0)
    win_rate_with_signal = Column(Float, nullable=True)
    win_rate_without_signal = Column(Float, nullable=True)
    last_recalc_at = Column(DateTime, nullable=True)


class MeteoraCooldown(Base):
    """Cooldown preventing re-entry into recently failed pools/mints."""

    __tablename__ = "meteora_cooldowns"
    __table_args__ = (Index("ix_meteora_cooldowns_scope", "scope", "target"),)

    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String)  # pool | base_mint (composite ix below)
    target = Column(String, index=True)  # address
    trigger = Column(String)  # e.g. oor_cooldown | blacklist | rug_screen
    event_count = Column(Integer, default=1)
    expires_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=_utcnow)
