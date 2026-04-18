"""Database models and connection for BTC 5-min trading bot."""

import logging
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    JSON,
    Text,
    text,
    UniqueConstraint,
    ForeignKey,
    Index,
)
from sqlalchemy import event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect

from backend.config import settings

logger = logging.getLogger(__name__)

_is_sqlite = "sqlite" in settings.DATABASE_URL

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
    pool_size=20 if _is_sqlite else 10,
    max_overflow=30 if _is_sqlite else 20,
    pool_recycle=1800,
    pool_timeout=60,
)


def configure_sqlite_wal(engine_obj):
    """Register a connect listener that enables WAL mode for SQLite connections."""
    if engine_obj.url.get_dialect().name != "sqlite":
        return

    @event.listens_for(engine_obj, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


configure_sqlite_wal(engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Trade(Base):
    """Simulated trades for tracking P&L."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(
        Integer,
        ForeignKey("signals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    market_ticker = Column(String, index=True)
    platform = Column(String)
    event_slug = Column(String, nullable=True)
    market_type = Column(String, default="btc", index=True)  # "btc" or "weather"

    # Trade details
    direction = Column(String)  # "up" or "down"
    entry_price = Column(Float)
    size = Column(Float)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Settlement
    settled = Column(Boolean, default=False)
    settlement_time = Column(DateTime, nullable=True)
    settlement_value = Column(Float, nullable=True)  # 1.0=Up won, 0.0=Down won
    result = Column(
        String, default="pending"
    )  # pending, win, loss, expired, push, closed
    pnl = Column(Float, nullable=True)

    # Model performance tracking
    model_probability = Column(Float)
    market_price_at_entry = Column(Float)
    edge_at_entry = Column(Float)

    # Trading mode this trade was placed in
    trading_mode = Column(String, default="paper", index=True)

    # Strategy tracking
    strategy = Column(String, nullable=True)
    signal_source = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)

    # Partial fill tracking
    filled_size = Column(
        Float, nullable=True
    )  # actual fill amount, None = assumed full fill

    # On-chain order tracking (testnet / live modes)
    clob_order_id = Column(
        String, nullable=True
    )  # Order ID returned by Polymarket CLOB
    clob_idempotency_key = Column(
        String, nullable=True
    )  # UUID idempotency key per order attempt

    # Market end date for settlement tracking (when the market expires)
    market_end_date = Column(DateTime, nullable=True, index=True)

    # Fee and slippage tracking
    fee = Column(Float, nullable=True)
    slippage = Column(Float, nullable=True)

    # Reconciliation fields for blockchain sync
    source = Column(String, nullable=False, default="bot", index=True)
    blockchain_verified = Column(Boolean, nullable=False, default=False)
    settlement_source = Column(String, nullable=True, default=None)
    last_sync_at = Column(DateTime, nullable=True, default=None, index=True)
    external_import_at = Column(DateTime, nullable=True, default=None)


class BtcPriceSnapshot(Base):
    """Cached BTC prices for momentum calculation."""

    __tablename__ = "btc_price_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    price = Column(Float)
    source = Column(String, default="coingecko")


class BotState(Base):
    """Bot state and statistics."""

    __tablename__ = "bot_state"

    id = Column(Integer, primary_key=True)
    mode = Column(String, primary_key=True, default="paper")
    bankroll = Column(Float, default=100.0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    last_run = Column(DateTime, nullable=True)
    is_running = Column(Boolean, default=False)

    # Sync metadata for reconciliation tracking
    last_sync_at = Column(DateTime, nullable=True, default=None)
    last_live_sync_error = Column(String, nullable=True, default=None)

    # Active wallet for multi-wallet management
    active_wallet = Column(String, nullable=True, index=True)

    # Paper trading tracking
    paper_bankroll = Column(Float, default=100.0)
    paper_pnl = Column(Float, default=0.0)
    paper_trades = Column(Integer, default=0)
    paper_wins = Column(Integer, default=0)

    # Testnet trading tracking (isolated from live)
    testnet_bankroll = Column(Float, default=100.0)
    testnet_pnl = Column(Float, default=0.0)
    testnet_trades = Column(Integer, default=0)
    testnet_wins = Column(Integer, default=0)

    # Generic JSON blob for strategy heartbeats and ad-hoc state
    misc_data = Column(Text, nullable=True)

    # Settlement verification tracking
    settlement_last_check_at = Column(DateTime, nullable=True, default=None)

    def __repr__(self):
        return (f"<BotState(id={self.id}, mode={self.mode}, bankroll={self.bankroll}, "
                f"total_pnl={self.total_pnl}, total_trades={self.total_trades}, "
                f"winning_trades={self.winning_trades})>")


class Signal(Base):
    """Trading signals generated by the bot."""

    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    market_ticker = Column(String, index=True)
    platform = Column(String)
    market_type = Column(String, default="btc", index=True)  # "btc" or "weather"
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    direction = Column(String)
    model_probability = Column(Float)
    market_price = Column(Float)
    edge = Column(Float)
    confidence = Column(Float)

    kelly_fraction = Column(Float)
    suggested_size = Column(Float)

    sources = Column(JSON)
    reasoning = Column(String)

    # Edge discovery tracking
    track_name = Column(
        String, nullable=True, default="legacy", index=True
    )  # Which edge track generated this signal
    execution_mode = Column(String, nullable=True, default="paper")  # 'paper' or 'live'
    token_id = Column(String, nullable=True)

    executed = Column(Boolean, default=False)

    # Calibration tracking — filled after settlement
    actual_outcome = Column(
        String, nullable=True
    )  # "up" or "down" — actual market result
    outcome_correct = Column(
        Boolean, nullable=True
    )  # did our direction prediction match?
    settlement_value = Column(Float, nullable=True)  # 1.0=UP won, 0.0=DOWN won
    settled_at = Column(DateTime, nullable=True)  # when we recorded the outcome


class AILog(Base):
    """Log of all AI API calls."""

    __tablename__ = "ai_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    provider = Column(String, index=True)
    model = Column(String)

    prompt = Column(String)
    response = Column(String)
    call_type = Column(String, index=True)

    latency_ms = Column(Float)
    tokens_used = Column(Integer)
    cost_usd = Column(Float)

    related_market = Column(String, nullable=True)
    success = Column(Boolean, default=True)
    error = Column(String, nullable=True)


class ScanLog(Base):
    """Log of each market scan run."""

    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    categories_scanned = Column(JSON)
    platforms_scanned = Column(JSON)

    markets_found = Column(Integer, default=0)
    signals_generated = Column(Integer, default=0)
    trades_executed = Column(Integer, default=0)

    ai_calls_made = Column(Integer, default=0)
    ai_cost_usd = Column(Float, default=0.0)

    success = Column(Boolean, default=True)
    error = Column(String, nullable=True)


class CopyTraderEntry(Base):
    """Copy trader position entries mirrored from tracked wallets."""

    __tablename__ = "copy_trader_entries"

    id = Column(Integer, primary_key=True)
    wallet = Column(String, nullable=False, index=True)
    condition_id = Column(String, nullable=False)
    side = Column(String, nullable=False)  # "YES" or "NO"
    size = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True, default=0.0)
    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("wallet", "condition_id", "side", name="uq_copy_entry"),
    )


class SettlementEvent(Base):
    __tablename__ = "settlement_events"

    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=False)
    market_ticker = Column(String, nullable=False, index=True)
    resolved_outcome = Column(String)  # "up", "down", "yes", "no"
    pnl = Column(Float)
    settled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source = Column(String, default="polymarket")  # "polymarket" or "kalshi"


class DecisionLog(Base):
    __tablename__ = "decision_log"
    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String, nullable=False, index=True)
    market_ticker = Column(String, nullable=False, index=True)
    decision = Column(String, nullable=False)  # BUY, SKIP, SELL, HOLD, ERROR
    confidence = Column(Float, nullable=True)
    signal_data = Column(Text, nullable=True)  # JSON string
    reason = Column(Text, nullable=True)
    outcome = Column(String, nullable=True)  # WIN, LOSS, PUSH — filled at settlement
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )


class MarketWatch(Base):
    __tablename__ = "market_watch"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, unique=True, index=True)
    category = Column(String, nullable=True)
    source = Column(String, nullable=True)  # strategy name or "user"
    config = Column(Text, nullable=True)  # JSON string
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class WalletConfig(Base):
    __tablename__ = "wallet_config"
    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, nullable=False, unique=True, index=True)
    pseudonym = Column(String, nullable=True)
    source = Column(String, default="user")  # "leaderboard", "user", "import"
    tags = Column(Text, nullable=True)  # JSON array string
    enabled = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    whale_score = Column(Float, nullable=True)
    balance_cache = Column(
        Text, nullable=True
    )  # JSON: {"usdc_balance", "last_updated"}


class StrategyConfig(Base):
    __tablename__ = "strategy_config"
    id = Column(Integer, primary_key=True, index=True)
    strategy_name = Column(String, nullable=False, unique=True, index=True)
    enabled = Column(Boolean, default=False)
    params = Column(Text, nullable=True)  # JSON string
    interval_seconds = Column(Integer, default=60)
    trading_mode = Column(
        String, nullable=True
    )  # "paper", "testnet", "live" - overrides global TRADING_MODE
    mode = Column(String, nullable=True, default=None)  # "paper", "testnet", "live" - NULL = applies to all modes
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TradeContext(Base):
    __tablename__ = "trade_context"
    trade_id = Column(Integer, ForeignKey("trades.id"), primary_key=True)
    strategy = Column(String, nullable=True)
    signal_source = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    entry_signal = Column(Text, nullable=True)  # JSON string
    exit_signal = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class JobQueue(Base):
    """Persistent job queue for crash recovery."""

    __tablename__ = "job_queue"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(50), nullable=False)
    idempotency_key = Column(String(255), nullable=True)
    priority = Column(String(20), default="medium")  # critical, high, medium, low
    status = Column(
        String(20), default="pending"
    )  # pending, processing, completed, failed
    payload = Column(JSON, nullable=False)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    scheduled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_job_queue_status_priority", "status", "priority"),
        UniqueConstraint("job_type", "idempotency_key", name="uq_job_idempotency"),
    )


class WhaleTransaction(Base):
    __tablename__ = "whale_transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String, unique=True, index=True, nullable=False)
    wallet = Column(String, index=True, nullable=False)
    market_id = Column(String, index=True, nullable=True)
    side = Column(String, nullable=True)  # buy/sell
    size_usd = Column(Float, nullable=False)
    block_number = Column(Integer, nullable=True)
    observed_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PendingApproval(Base):
    __tablename__ = "pending_approvals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, index=True, nullable=False)
    direction = Column(String, nullable=False)
    size = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    signal_data = Column(JSON, nullable=True)
    status = Column(String, default="pending")  # pending|approved|rejected
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    decided_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    """Comprehensive audit log for all money-related operations."""
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    event_type = Column(String, nullable=False, index=True)  # TRADE_CREATED, SETTLEMENT_COMPLETED, POSITION_UPDATED, WALLET_RECONCILED
    entity_type = Column(String, nullable=False)  # TRADE, POSITION, WALLET, CONFIG
    entity_id = Column(String, nullable=False, index=True)  # trade_id, position_id, wallet_address
    old_value = Column(JSON, nullable=True)  # Previous state snapshot
    new_value = Column(JSON, nullable=True)  # New state snapshot
    user_id = Column(String, default="system")  # "system", "admin", "strategy:btc_5min"
    
    # Legacy fields for backward compatibility
    actor = Column(String, default="system")
    action = Column(String, nullable=True)
    details = Column(JSON, nullable=True)


class Experiment(Base):
    """Track parameter experiments for each strategy."""

    __tablename__ = "experiments"
    id = Column(Integer, primary_key=True, index=True)
    strategy_name = Column(String, nullable=False, index=True)
    params_json = Column(JSON, nullable=False)
    metrics_json = Column(JSON, nullable=True)
    status = Column(String, default="candidate")  # candidate|active|retired
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    promoted_at = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)


class EquitySnapshot(Base):
    """Daily equity curve snapshots for performance tracking."""

    __tablename__ = "equity_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    bankroll = Column(Float, nullable=False)
    total_pnl = Column(Float, default=0.0)
    open_exposure = Column(Float, default=0.0)
    strategy_allocations = Column(JSON, nullable=True)
    trade_count = Column(Integer, default=0)
    win_count = Column(Integer, default=0)


class CalibrationRecord(Base):
    """Track predicted probability vs actual outcome for model calibration."""

    __tablename__ = "calibration_records"
    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String, nullable=False, index=True)
    market_ticker = Column(String, nullable=False)
    predicted_prob = Column(Float, nullable=False)
    direction = Column(String, nullable=False)
    actual_outcome = Column(String, nullable=True)  # "win"|"loss"|None (pending)
    settlement_value = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ResearchItemDB(Base):
    __tablename__ = "research_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    source = Column(String, nullable=False)
    url = Column(String, nullable=False)
    content_summary = Column(String)
    relevance_score = Column(Float, nullable=False)
    fingerprint = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    used_in_decision = Column(Boolean, default=False)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    ensure_schema()


def ensure_schema():
    """Ensure newer schema fields exist even if migration wasn't run."""
    inspector = inspect(engine)

    try:
        columns = [col["name"] for col in inspector.get_columns("trades")]
    except Exception:
        return

    if "event_slug" not in columns:
        stmt = "ALTER TABLE trades ADD COLUMN event_slug VARCHAR"
        if engine.dialect.name not in ("sqlite", "mysql"):
            stmt = "ALTER TABLE trades ADD COLUMN IF NOT EXISTS event_slug VARCHAR"

        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text(stmt))

    if "market_type" not in columns:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(
                        "ALTER TABLE trades ADD COLUMN market_type VARCHAR DEFAULT 'btc'"
                    )
                )

    if "trading_mode" not in columns:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(
                        "ALTER TABLE trades ADD COLUMN trading_mode VARCHAR DEFAULT 'paper'"
                    )
                )
        try:
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(
                        text(
                            "UPDATE trades SET trading_mode = 'paper' WHERE trading_mode IS NULL"
                        )
                    )
        except Exception as e:
            logger.warning(f"Schema migration: could not backfill trading_mode: {e}")

    # Add paper tracking columns to bot_state
    try:
        bot_state_columns = [col["name"] for col in inspector.get_columns("bot_state")]
    except Exception:
        bot_state_columns = []

    if bot_state_columns:
        with engine.connect() as conn:
            for col, coltype in [
                ("paper_bankroll", "FLOAT DEFAULT 10000.0"),
                ("paper_pnl", "FLOAT DEFAULT 0.0"),
                ("paper_trades", "INTEGER DEFAULT 0"),
                ("paper_wins", "INTEGER DEFAULT 0"),
                ("testnet_bankroll", "FLOAT DEFAULT 100.0"),
                ("testnet_pnl", "FLOAT DEFAULT 0.0"),
                ("testnet_trades", "INTEGER DEFAULT 0"),
                ("testnet_wins", "INTEGER DEFAULT 0"),
                ("misc_data", "TEXT"),
                ("active_wallet", "TEXT"),
            ]:
                if col not in bot_state_columns:
                    try:
                        with conn.begin():
                            conn.execute(
                                text(
                                    f"ALTER TABLE bot_state ADD COLUMN {col} {coltype}"
                                )
                            )
                    except Exception as e:
                        logger.warning(
                            f"Schema migration: could not add bot_state column {col}: {e}"
                        )

    # Add calibration columns to signals table
    try:
        signal_columns = [col["name"] for col in inspector.get_columns("signals")]
    except Exception:
        signal_columns = []

    if signal_columns:
        with engine.connect() as conn:
            for col, coltype in [
                ("actual_outcome", "TEXT"),
                ("outcome_correct", "BOOLEAN"),
                ("settlement_value", "FLOAT"),
                ("settled_at", "DATETIME"),
                ("market_type", "VARCHAR DEFAULT 'btc'"),
            ]:
                if col not in signal_columns:
                    try:
                        with conn.begin():
                            conn.execute(
                                text(f"ALTER TABLE signals ADD COLUMN {col} {coltype}")
                            )
                    except Exception as e:
                        logger.warning(
                            f"Schema migration: could not add signals column {col}: {e}"
                        )

    # Add edge discovery tracking columns to signals table
    with engine.connect() as conn:
        for col, coltype in [
            (
                "track_name",
                "VARCHAR DEFAULT 'legacy'",
            ),  # Which edge track generated this signal
            ("execution_mode", "VARCHAR DEFAULT 'paper'"),  # 'paper' or 'live'
        ]:
            if col not in signal_columns:
                try:
                    with conn.begin():
                        conn.execute(
                            text(f"ALTER TABLE signals ADD COLUMN {col} {coltype}")
                        )
                except Exception as e:
                    logger.warning(
                        f"Schema migration: could not add signals edge-track column {col}: {e}"
                    )

    try:
        bot_state_columns = {col["name"] for col in inspector.get_columns("bot_state")}
    except Exception:
        bot_state_columns = set()

    if bot_state_columns and "mode" not in bot_state_columns:
        try:
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(
                        text("ALTER TABLE bot_state ADD COLUMN mode VARCHAR DEFAULT 'paper'")
                    )
                    logger.info("Added 'mode' column to bot_state")
        except Exception as e:
            logger.warning(f"Schema migration: could not add bot_state.mode: {e}")

        try:
            with engine.connect() as conn:
                with conn.begin():
                    result = conn.execute(
                        text("SELECT COUNT(*) FROM bot_state")
                    )
                    count = result.scalar()
                    
                    if count == 1:
                        result = conn.execute(
                            text("SELECT id, bankroll, total_trades, winning_trades, total_pnl, "
                                 "paper_bankroll, paper_pnl, paper_trades, paper_wins, "
                                 "testnet_bankroll, testnet_pnl, testnet_trades, testnet_wins "
                                 "FROM bot_state LIMIT 1")
                        )
                        row = result.fetchone()
                        
                        if row:
                            (id_val, bankroll, total_trades, winning_trades, total_pnl,
                             paper_bankroll, paper_pnl, paper_trades, paper_wins,
                             testnet_bankroll, testnet_pnl, testnet_trades, testnet_wins) = row
                            
                            conn.execute(
                                text("UPDATE bot_state SET bankroll = :bankroll, "
                                     "total_trades = :total_trades, winning_trades = :winning_trades, "
                                     "total_pnl = :total_pnl WHERE id = :id"),
                                {"bankroll": paper_bankroll or bankroll, 
                                 "total_trades": paper_trades or total_trades,
                                 "winning_trades": paper_wins or winning_trades,
                                 "total_pnl": paper_pnl or total_pnl,
                                 "id": id_val}
                            )
                            logger.info("Migrated existing bot_state row to paper mode")
        except Exception as e:
            logger.warning(f"Schema migration: could not migrate bot_state to mode-based schema: {e}")

    # Add per-track bankroll and PNL tracking to bot_state
    try:
        bot_state_columns = [col["name"] for col in inspector.get_columns("bot_state")]
    except Exception:
        bot_state_columns = []

    if bot_state_columns:
        with engine.connect() as conn:
            for col, coltype in [
                # Per-track bankrolls (for isolation)
                ("track_bankroll_realtime", "FLOAT DEFAULT 100.0"),
                ("track_bankroll_whale", "FLOAT DEFAULT 100.0"),
                ("track_bankroll_commodity", "FLOAT DEFAULT 100.0"),
                # Per-track PNL tracking
                ("track_pnl_realtime", "FLOAT DEFAULT 0.0"),
                ("track_pnl_whale", "FLOAT DEFAULT 0.0"),
                ("track_pnl_commodity", "FLOAT DEFAULT 0.0"),
                # Per-track loss limits
                ("track_loss_limit_realtime", "FLOAT DEFAULT 50.0"),
                ("track_loss_limit_whale", "FLOAT DEFAULT 50.0"),
                ("track_loss_limit_commodity", "FLOAT DEFAULT 50.0"),
            ]:
                if col not in bot_state_columns:
                    try:
                        with conn.begin():
                            conn.execute(
                                text(
                                    f"ALTER TABLE bot_state ADD COLUMN {col} {coltype}"
                                )
                            )
                    except Exception as e:
                        logger.warning(
                            f"Schema migration: could not add bot_state per-track column {col}: {e}"
                        )

    # Ensure copy_trader_entries table exists
    try:
        copy_entry_tables = inspector.get_table_names()
    except Exception:
        copy_entry_tables = []

    if "copy_trader_entries" not in copy_entry_tables:
        CopyTraderEntry.__table__.create(bind=engine, checkfirst=True)
    else:
        # Migrate: add pnl column if missing
        try:
            copy_cols = {
                c["name"] for c in inspector.get_columns("copy_trader_entries")
            }
            if "pnl" not in copy_cols:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text(
                                "ALTER TABLE copy_trader_entries ADD COLUMN pnl REAL DEFAULT 0.0"
                            )
                        )
        except Exception as e:
            logger.warning(
                f"Schema migration: could not add copy_trader_entries pnl column: {e}"
            )

    # Ensure settlement_events table exists
    if "settlement_events" not in copy_entry_tables:
        SettlementEvent.__table__.create(bind=engine, checkfirst=True)

    # Ensure audit_log table exists
    if "audit_log" not in copy_entry_tables:
        AuditLog.__table__.create(bind=engine, checkfirst=True)

    # Ensure new tables exist (DecisionLog, MarketWatch, WalletConfig, StrategyConfig, TradeContext)
    Base.metadata.create_all(bind=engine)

    # Add whale_score column to wallet_config if missing
    try:
        wallet_columns = {col["name"] for col in inspector.get_columns("wallet_config")}
        if "whale_score" not in wallet_columns:
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(
                        text("ALTER TABLE wallet_config ADD COLUMN whale_score FLOAT")
                    )
    except Exception as e:
        logger.warning(
            f"Schema migration: could not add wallet_config whale_score column: {e}"
        )

    # Add new columns to trades table if missing
    inspector = inspect(engine)
    existing_cols = {col["name"] for col in inspector.get_columns("trades")}
    with engine.connect() as conn:
        for col_def in [
            "ALTER TABLE trades ADD COLUMN strategy TEXT",
            "ALTER TABLE trades ADD COLUMN signal_source TEXT",
            "ALTER TABLE trades ADD COLUMN confidence REAL",
            "ALTER TABLE trades ADD COLUMN clob_order_id TEXT",
            "ALTER TABLE trades ADD COLUMN clob_idempotency_key TEXT",
            "ALTER TABLE trades ADD COLUMN filled_size REAL",
        ]:
            col_name = col_def.split("ADD COLUMN ")[1].split()[0]
            if col_name not in existing_cols:
                with conn.begin():
                    conn.execute(text(col_def))

    # Create indexes for hot query paths
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_trades_settled_mode ON trades(settled, trading_mode)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_trades_ticker_settled ON trades(market_ticker, settled)"
                    )
                )
    except Exception as e:
        logger.warning(f"Could not create trades indexes: {e}")

    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_pending_approvals_status ON pending_approvals(status)"
                    )
                )
    except Exception as e:
        logger.warning(f"Could not create pending_approvals index: {e}")

    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_settlement_events_trade_id ON settlement_events(trade_id)"
                    )
                )
    except Exception as e:
        logger.warning(f"Could not create settlement_events index: {e}")

    # Migration: Add unified state sync columns to trades table
    inspector = inspect(engine)
    try:
        existing_cols = {col["name"] for col in inspector.get_columns("trades")}
    except Exception:
        existing_cols = set()

    if existing_cols:
        # NEW FIELD 1: source
        if "source" not in existing_cols:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE trades ADD COLUMN source VARCHAR DEFAULT 'bot'")
                        )
                        logger.info("Added 'source' column to trades")
            except Exception as e:
                logger.warning(f"Schema migration: could not add trades.source: {e}")

        # NEW FIELD 2: blockchain_verified
        if "blockchain_verified" not in existing_cols:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE trades ADD COLUMN blockchain_verified BOOLEAN DEFAULT 0")
                        )
                        logger.info("Added 'blockchain_verified' column to trades")
            except Exception as e:
                logger.warning(f"Schema migration: could not add trades.blockchain_verified: {e}")

        # NEW FIELD 3: settlement_source
        if "settlement_source" not in existing_cols:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE trades ADD COLUMN settlement_source VARCHAR DEFAULT NULL")
                        )
                        logger.info("Added 'settlement_source' column to trades")
            except Exception as e:
                logger.warning(f"Schema migration: could not add trades.settlement_source: {e}")

        # NEW FIELD 4: last_sync_at
        if "last_sync_at" not in existing_cols:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE trades ADD COLUMN last_sync_at DATETIME DEFAULT NULL")
                        )
                        logger.info("Added 'last_sync_at' column to trades")
            except Exception as e:
                logger.warning(f"Schema migration: could not add trades.last_sync_at: {e}")

        # NEW FIELD 5: external_import_at
        if "external_import_at" not in existing_cols:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE trades ADD COLUMN external_import_at DATETIME DEFAULT NULL")
                        )
                        logger.info("Added 'external_import_at' column to trades")
            except Exception as e:
                logger.warning(f"Schema migration: could not add trades.external_import_at: {e}")

    # Migration: Add unified state sync columns to bot_state table
    try:
        bot_state_columns = {col["name"] for col in inspector.get_columns("bot_state")}
    except Exception:
        bot_state_columns = set()

    if bot_state_columns:
        # NEW FIELD 1: last_sync_at
        if "last_sync_at" not in bot_state_columns:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE bot_state ADD COLUMN last_sync_at DATETIME DEFAULT NULL")
                        )
                        logger.info("Added 'last_sync_at' column to bot_state")
            except Exception as e:
                logger.warning(f"Schema migration: could not add bot_state.last_sync_at: {e}")

        # NEW FIELD 2: last_live_sync_error
        if "last_live_sync_error" not in bot_state_columns:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE bot_state ADD COLUMN last_live_sync_error VARCHAR DEFAULT NULL")
                        )
                        logger.info("Added 'last_live_sync_error' column to bot_state")
            except Exception as e:
                logger.warning(f"Schema migration: could not add bot_state.last_live_sync_error: {e}")

        # NEW FIELD 3: settlement_last_check_at
        if "settlement_last_check_at" not in bot_state_columns:
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(
                            text("ALTER TABLE bot_state ADD COLUMN settlement_last_check_at DATETIME DEFAULT NULL")
                        )
                        logger.info("Added 'settlement_last_check_at' column to bot_state")
            except Exception as e:
                logger.warning(f"Schema migration: could not add bot_state.settlement_last_check_at: {e}")

    # Create indexes for new fields
    try:
        with engine.connect() as conn:
            with conn.begin():
                # Index for source filtering (Tasks 6-10, Task 11)
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_trades_source ON trades(source)")
                )
                # Index for last_sync_at filtering
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_trades_last_sync_at ON trades(last_sync_at)")
                )
                # Index for blockchain_verified filtering
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_trades_blockchain_verified ON trades(blockchain_verified)")
                )
                # Index for clob_order_id uniqueness check (Task 5)
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_trades_clob_order_id ON trades(clob_order_id)")
                )
                logger.info("Created indexes for unified state sync fields")
    except Exception as e:
        logger.warning(f"Could not create unified state sync indexes: {e}")

    # Backfill logic for existing trades (preserve data)
    try:
        with engine.connect() as conn:
            with conn.begin():
                # Set source="bot" for all existing trades (assume bot-executed)
                conn.execute(
                    text("UPDATE trades SET source = 'bot' WHERE source IS NULL")
                )
                logger.info("Backfilled 'source' field for existing trades")

                # Set blockchain_verified=0 for all existing trades (conservative)
                conn.execute(
                    text("UPDATE trades SET blockchain_verified = 0 WHERE blockchain_verified IS NULL")
                )
                logger.info("Backfilled 'blockchain_verified' field for existing trades")
    except Exception as e:
        logger.warning(f"Could not backfill unified state sync fields: {e}")

    # Add mode column to strategy_config for per-mode strategy control
    try:
        strategy_config_columns = {col["name"] for col in inspector.get_columns("strategy_config")}
    except Exception:
        strategy_config_columns = set()

    if strategy_config_columns and "mode" not in strategy_config_columns:
        try:
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(
                        text("ALTER TABLE strategy_config ADD COLUMN mode TEXT")
                    )
                    logger.info("Added 'mode' column to strategy_config")
        except Exception as e:
            logger.warning(f"Schema migration: could not add strategy_config.mode: {e}")


def log_audit(action: str, actor: str = "system", details: dict = None):
    db = SessionLocal()
    try:
        entry = AuditLog(action=action, actor=actor, details=details)
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
