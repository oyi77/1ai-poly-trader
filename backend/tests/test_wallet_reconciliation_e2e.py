"""
End-to-end integration tests for wallet reconciliation logic.

Tests the complete sync flow:
1. Database recovery from empty via sync_wallet
2. External trade detection (auto import)
3. Settlement verification mapping (detecting external closures & calculating PnL)
4. Orphan detection (position missing on CLOB is marked as orphaned)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import Base, Trade
from backend.core.wallet_reconciliation import WalletReconciler, SyncResult
from backend.data.polymarket_clob import PolymarketCLOB, TradeRecord


# ---------------------------------------------------------------------------
# In-memory SQLite fixture (per-test isolation)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    """Provide a fresh in-memory SQLite session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def mock_clob():
    """Mock PolymarketCLOB client with builder_address set."""
    clob = MagicMock(spec=PolymarketCLOB)
    clob.builder_address = "0xTEST_WALLET_ADDRESS"
    clob.get_wallet_trades = AsyncMock(return_value=[])
    clob.get_trader_positions = AsyncMock(return_value=[])
    return clob


# ---------------------------------------------------------------------------
# Test 1: Database Recovery from Empty (Import Historical Trades)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_database_recovery_from_empty(db, mock_clob):
    """
    Scenario: Empty database, blockchain has 3 historical trades.
    Expected: All 3 trades imported with source='external'.
    """
    # Mock blockchain history with 3 trades
    mock_clob.get_wallet_trades.return_value = [
        TradeRecord(
            id="trade_001",
            user="0xTEST_WALLET_ADDRESS",
            asset_id="0xMARKET_A",
            outcome="YES",
            shares=100.0,
            price=0.65,
            spent=65.0,
            timestamp=int(datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp()),
            transaction_hash="0xhash1",
            block_number=12345,
        ),
        TradeRecord(
            id="trade_002",
            user="0xTEST_WALLET_ADDRESS",
            asset_id="0xMARKET_B",
            outcome="NO",
            shares=50.0,
            price=0.40,
            spent=20.0,
            timestamp=int(datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc).timestamp()),
            transaction_hash="0xhash2",
            block_number=12346,
        ),
        TradeRecord(
            id="trade_003",
            user="0xTEST_WALLET_ADDRESS",
            asset_id="0xMARKET_C",
            outcome="YES",
            shares=200.0,
            price=0.55,
            spent=110.0,
            timestamp=int(datetime(2026, 4, 3, 9, 15, 0, tzinfo=timezone.utc).timestamp()),
            transaction_hash="0xhash3",
            block_number=12347,
        ),
    ]

    # Initialize reconciler
    reconciler = WalletReconciler(clob_client=mock_clob, db=db, mode="testnet")

    # Run import
    imported_count = await reconciler.import_blockchain_history(max_pages=1)

    # Verify: 3 trades imported
    assert imported_count == 3

    # Verify: All trades in DB with correct attributes
    trades = db.query(Trade).all()
    assert len(trades) == 3

    # Check first trade
    trade1 = db.query(Trade).filter(Trade.clob_order_id == "trade_001").first()
    assert trade1 is not None
    assert trade1.market_ticker == "0xMARKET_A"
    assert trade1.direction == "up"  # YES -> up
    assert trade1.entry_price == 0.65
    assert trade1.size == 100.0
    assert trade1.source == "external"
    assert trade1.blockchain_verified is True
    assert trade1.settlement_source == "data_api"
    assert trade1.external_import_at is not None

    # Check second trade (NO -> down)
    trade2 = db.query(Trade).filter(Trade.clob_order_id == "trade_002").first()
    assert trade2 is not None
    assert trade2.direction == "down"  # NO -> down
    assert trade2.entry_price == 0.40
    assert trade2.size == 50.0


# ---------------------------------------------------------------------------
# Test 2: External Trade Detection (Deduplication)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_external_trade_deduplication(db, mock_clob):
    """
    Scenario: DB has 1 trade, blockchain returns same trade + 1 new trade.
    Expected: Only the new trade is imported (no duplicates).
    """
    # Seed DB with existing trade
    existing_trade = Trade(
        market_ticker="0xMARKET_A",
        platform="polymarket",
        direction="up",
        entry_price=0.65,
        size=100.0,
        timestamp=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        trading_mode="testnet",
        source="external",
        clob_order_id="trade_001",
        blockchain_verified=True,
        settlement_source="data_api",
        model_probability=0.5,
        market_price_at_entry=0.65,
        edge_at_entry=0.0,
    )
    db.add(existing_trade)
    db.commit()

    # Mock blockchain history: same trade + new trade
    mock_clob.get_wallet_trades.return_value = [
        TradeRecord(
            id="trade_001",  # Duplicate
            user="0xTEST_WALLET_ADDRESS",
            asset_id="0xMARKET_A",
            outcome="YES",
            shares=100.0,
            price=0.65,
            spent=65.0,
            timestamp=int(datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp()),
        ),
        TradeRecord(
            id="trade_004",  # New
            user="0xTEST_WALLET_ADDRESS",
            asset_id="0xMARKET_D",
            outcome="NO",
            shares=75.0,
            price=0.30,
            spent=22.5,
            timestamp=int(datetime(2026, 4, 4, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
        ),
    ]

    reconciler = WalletReconciler(clob_client=mock_clob, db=db, mode="testnet")
    imported_count = await reconciler.import_blockchain_history(max_pages=1)

    # Verify: Only 1 new trade imported
    assert imported_count == 1

    # Verify: Total 2 trades in DB
    trades = db.query(Trade).all()
    assert len(trades) == 2

    # Verify: New trade exists
    new_trade = db.query(Trade).filter(Trade.clob_order_id == "trade_004").first()
    assert new_trade is not None
    assert new_trade.market_ticker == "0xMARKET_D"


# ---------------------------------------------------------------------------
# Test 3: Settlement Verification (Detecting External Closures)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settlement_verification_external_closure(db, mock_clob):
    """
    Scenario: DB has 2 open trades, blockchain shows only 1 still open.
    Expected: The missing trade is marked as closed with settlement_source='clob_api'.
    """
    # Seed DB with 2 open trades
    trade1 = Trade(
        market_ticker="0xMARKET_A",
        platform="polymarket",
        direction="up",
        entry_price=0.65,
        size=100.0,
        timestamp=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        trading_mode="testnet",
        source="bot",
        settled=False,
        settlement_time=None,
        model_probability=0.7,
        market_price_at_entry=0.65,
        edge_at_entry=0.05,
    )
    trade2 = Trade(
        market_ticker="0xMARKET_B",
        platform="polymarket",
        direction="down",
        entry_price=0.40,
        size=50.0,
        timestamp=datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc),
        trading_mode="testnet",
        source="bot",
        settled=False,
        settlement_time=None,
        model_probability=0.6,
        market_price_at_entry=0.40,
        edge_at_entry=0.10,
    )
    db.add_all([trade1, trade2])
    db.commit()

    # Mock blockchain: only MARKET_A still open
    mock_clob.get_trader_positions.return_value = [
        {
            "asset_id": "0xMARKET_A",
            "order_id": "order_001",
            "size": 100.0,
            "avg_price": 0.65,
            "outcome": "YES",
            "timestamp": "2026-04-01T10:00:00Z",
            "exit_timestamp": None,
        }
    ]

    reconciler = WalletReconciler(clob_client=mock_clob, db=db, mode="testnet")
    result = await reconciler.sync_current_positions()

    # Verify: 1 updated, 1 closed
    assert result.updated_count == 1
    assert result.closed_count == 1

    # Verify: MARKET_A still open
    trade1_updated = db.query(Trade).filter(Trade.market_ticker == "0xMARKET_A").first()
    assert trade1_updated.settled is False
    assert trade1_updated.last_sync_at is not None
    assert trade1_updated.blockchain_verified is True

    # Verify: MARKET_B marked as closed
    trade2_closed = db.query(Trade).filter(Trade.market_ticker == "0xMARKET_B").first()
    assert trade2_closed.settled is True
    assert trade2_closed.settlement_time is not None
    assert trade2_closed.settlement_source == "clob_api"
    assert trade2_closed.blockchain_verified is True
    assert trade2_closed.result == "closed"


# ---------------------------------------------------------------------------
# Test 4: Orphan Detection (Position on Blockchain but Missing in DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphan_detection(db, mock_clob):
    """
    Scenario: Blockchain has 2 open positions, DB has only 1.
    Expected: The missing position is detected as orphaned.
    """
    # Seed DB with 1 open trade
    trade1 = Trade(
        market_ticker="0xMARKET_A",
        platform="polymarket",
        direction="up",
        entry_price=0.65,
        size=100.0,
        timestamp=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        trading_mode="testnet",
        source="bot",
        settled=False,
        model_probability=0.7,
        market_price_at_entry=0.65,
        edge_at_entry=0.05,
    )
    db.add(trade1)
    db.commit()

    # Mock blockchain: 2 open positions (MARKET_A + MARKET_X)
    mock_clob.get_trader_positions.return_value = [
        {
            "asset_id": "0xMARKET_A",
            "order_id": "order_001",
            "size": 100.0,
            "avg_price": 0.65,
            "outcome": "YES",
            "timestamp": "2026-04-01T10:00:00Z",
            "exit_timestamp": None,
        },
        {
            "asset_id": "0xMARKET_X",  # Orphaned
            "order_id": "order_orphan",
            "size": 150.0,
            "avg_price": 0.50,
            "outcome": "NO",
            "timestamp": "2026-04-05T08:00:00Z",
            "exit_timestamp": None,
        },
    ]

    reconciler = WalletReconciler(clob_client=mock_clob, db=db, mode="testnet")
    orphans = await reconciler.detect_orphaned_positions()

    # Verify: 1 orphan detected
    assert len(orphans) == 1
    assert orphans[0].market_id == "0xMARKET_X"
    assert orphans[0].blockchain_size == 150.0
    assert orphans[0].blockchain_entry_price == 0.50
    assert orphans[0].clob_order_id == "order_orphan"


# ---------------------------------------------------------------------------
# Test 5: Full Reconciliation E2E Flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_reconciliation_e2e(db, mock_clob):
    """
    Scenario: Complete reconciliation cycle with:
    - 2 historical trades to import
    - 1 open position to sync
    - 1 orphaned position to create
    Expected: All operations succeed, metrics correct.
    """
    # Mock blockchain history: 2 trades
    mock_clob.get_wallet_trades.return_value = [
        TradeRecord(
            id="trade_001",
            user="0xTEST_WALLET_ADDRESS",
            asset_id="0xMARKET_A",
            outcome="YES",
            shares=100.0,
            price=0.65,
            spent=65.0,
            timestamp=int(datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp()),
        ),
        TradeRecord(
            id="trade_002",
            user="0xTEST_WALLET_ADDRESS",
            asset_id="0xMARKET_B",
            outcome="NO",
            shares=50.0,
            price=0.40,
            spent=20.0,
            timestamp=int(datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc).timestamp()),
        ),
    ]

    # Mock blockchain positions: MARKET_A still open + MARKET_X orphaned
    mock_clob.get_trader_positions.return_value = [
        {
            "asset_id": "0xMARKET_A",
            "order_id": "order_001",
            "size": 100.0,
            "avg_price": 0.65,
            "outcome": "YES",
            "timestamp": "2026-04-01T10:00:00Z",
            "exit_timestamp": None,
        },
        {
            "asset_id": "0xMARKET_X",  # Orphaned
            "order_id": "order_orphan",
            "size": 150.0,
            "avg_price": 0.50,
            "outcome": "NO",
            "timestamp": "2026-04-05T08:00:00Z",
            "exit_timestamp": None,
        },
    ]

    reconciler = WalletReconciler(clob_client=mock_clob, db=db, mode="testnet")
    result = await reconciler.full_reconciliation()

    # Verify: Metrics correct
    assert result.imported_count == 2
    assert result.updated_count == 1
    assert result.closed_count == 2
    assert len(result.errors) == 0
    assert result.last_sync_at is not None

    # Verify: DB state
    trades = db.query(Trade).all()
    assert len(trades) == 3  # trade_001, trade_002, orphan MARKET_X

    # Verify: Orphan created
    orphan = db.query(Trade).filter(Trade.market_ticker == "0xMARKET_X").first()
    assert orphan is not None
    assert orphan.source == "orphaned"
    assert orphan.blockchain_verified is True
    assert orphan.size == 150.0
    assert orphan.entry_price == 0.50

    # Verify: MARKET_A synced
    market_a = db.query(Trade).filter(Trade.market_ticker == "0xMARKET_A").first()
    assert market_a.last_sync_at is not None
    assert market_a.blockchain_verified is True

    # Verify: MARKET_B closed (not on blockchain anymore)
    market_b = db.query(Trade).filter(Trade.market_ticker == "0xMARKET_B").first()
    assert market_b.settled is True
    assert market_b.settlement_source == "clob_api"
