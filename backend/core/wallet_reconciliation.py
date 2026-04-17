"""
Wallet reconciliation module for blockchain sync.

Orchestrates wallet reconciliation strategy, position comparison, trade imports,
and orphan detection. Called by background sync jobs.

Key responsibilities:
- Import historical trades from Polymarket Data API
- Sync current open positions from CLOB API
- Detect orphaned positions (on-chain but missing from DB)
- Close orphaned positions with metadata tracking
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.data.polymarket_clob import PolymarketCLOB, TradeRecord
from backend.models.database import Trade

logger = logging.getLogger("wallet_reconciler")


@dataclass
class PositionComparison:
    """Result of comparing blockchain vs DB position."""
    market_id: str
    db_status: str  # "open" | "closed" | "missing"
    blockchain_status: str
    db_size: float
    blockchain_size: float
    discrepancy: bool


@dataclass
class OrphanedPosition:
    """Position on blockchain but missing from DB."""
    market_id: str
    blockchain_size: float
    blockchain_entry_price: float
    clob_order_id: Optional[str] = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SyncResult:
    """Reconciliation cycle result."""
    imported_count: int = 0
    updated_count: int = 0
    closed_count: int = 0
    errors: list[str] = field(default_factory=list)
    last_sync_at: Optional[datetime] = None


class WalletReconciler:
    """Reconcile blockchain state with local database."""

    def __init__(self, clob_client: PolymarketCLOB, db: Session, mode: str):
        """
        Initialize wallet reconciler.

        Args:
            clob_client: PolymarketCLOB instance for API calls
            db: SQLAlchemy session
            mode: Trading mode ("live" | "testnet")
        """
        self.clob = clob_client
        self.db = db
        self.mode = mode
        
        # Determine wallet address from CLOB client
        if self.clob.builder_address:
            self.wallet_address = self.clob.builder_address
        elif hasattr(self.clob, '_account') and self.clob._account:
            self.wallet_address = self.clob._account.address
        else:
            raise ValueError(
                "Cannot determine wallet address from CLOB client. "
                "Ensure POLYMARKET_BUILDER_ADDRESS is set or client is initialized with private_key."
            )
        
        self.logger = logging.getLogger(f"wallet_reconciler[{mode}]")
        self.logger.info(f"Initialized reconciler for wallet {self.wallet_address}")

    async def full_reconciliation(self) -> SyncResult:
        """
        Complete wallet reconciliation cycle.

        Steps:
        1. Import blockchain history (all trades ever)
        2. Sync current positions (open orders)
        3. Detect orphaned positions (on-chain but missing locally)
        4. Close orphaned positions

        Returns:
            SyncResult with metrics (imported, updated, closed counts)
        """
        result = SyncResult()
        
        try:
            # 1. Import historical trades from blockchain
            self.logger.info("Starting full reconciliation cycle")
            imported = await self.import_blockchain_history(max_pages=None)
            result.imported_count = imported
            
            # 2. Sync current open positions
            position_result = await self.sync_current_positions()
            result.updated_count = position_result.updated_count
            result.closed_count = position_result.closed_count
            result.errors.extend(position_result.errors)
            
            # 3. Check for orphaned positions
            orphans = await self.detect_orphaned_positions()
            for orphan in orphans:
                try:
                    closed = await self.close_orphaned_position(orphan)
                    if closed:
                        result.closed_count += 1
                except Exception as e:
                    error_msg = f"Failed to close orphan {orphan.market_id}: {e}"
                    self.logger.error(error_msg, exc_info=True)
                    result.errors.append(error_msg)
            
            # 4. Update timestamps
            result.last_sync_at = datetime.now(timezone.utc)
            self.logger.info(
                f"Reconciliation complete: imported={result.imported_count}, "
                f"updated={result.updated_count}, closed={result.closed_count}, "
                f"errors={len(result.errors)}"
            )
            
        except Exception as e:
            error_msg = f"Reconciliation failed: {e}"
            self.logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)
        
        return result

    async def import_blockchain_history(self, max_pages: Optional[int] = None) -> int:
        """
        Download ALL historical trades from blockchain.

        Fetches from Data API using get_wallet_trades().
        Imports trades with source='external' if they don't exist locally.
        Deduplicates by clob_order_id or market+timestamp.

        Args:
            max_pages: Max pages to fetch. If None, fetches all pages.

        Returns:
            Count of newly imported trades
        """
        self.logger.info(f"Importing blockchain history for {self.wallet_address}")
        
        try:
            # Fetch blockchain history using Task 2's method
            trades = await self.clob.get_wallet_trades(
                wallet_address=self.wallet_address,
                limit=1000,
                max_pages=max_pages
            )
            
            self.logger.info(f"Downloaded {len(trades)} trades from blockchain")
            
            imported = 0
            for trade_record in trades:
                # Check if trade already exists by clob_order_id or market+timestamp
                existing = self.db.query(Trade).filter(
                    (Trade.clob_order_id == trade_record.id) |
                    (
                        (Trade.market_ticker == trade_record.asset_id) &
                        (Trade.timestamp == trade_record.created_at)
                    )
                ).first()
                
                if existing:
                    # Trade already in DB - skip
                    self.logger.debug(f"Trade {trade_record.id} already in DB (id={existing.id})")
                    continue
                
                # New external trade - import it
                new_trade = Trade(
                    market_ticker=trade_record.asset_id,
                    platform="polymarket",
                    direction="up" if trade_record.outcome == "YES" else "down",
                    entry_price=trade_record.price,
                    size=trade_record.shares,
                    timestamp=trade_record.created_at,
                    trading_mode=self.mode,
                    
                    # Reconciliation fields (Task 1)
                    source="external",                    # Manual trade or bot-placed outside
                    clob_order_id=trade_record.id,
                    blockchain_verified=True,            # Came from blockchain
                    settlement_source="data_api",        # From Polymarket Data API
                    external_import_at=datetime.now(timezone.utc),
                    
                    # Default values for required fields
                    model_probability=0.5,  # Unknown for external trades
                    market_price_at_entry=trade_record.price,
                    edge_at_entry=0.0,  # Unknown for external trades
                )
                
                self.db.add(new_trade)
                imported += 1
                self.logger.info(
                    f"Imported external trade: {trade_record.id} "
                    f"({trade_record.outcome} @ {trade_record.price}, {trade_record.shares} shares)"
                )
            
            self.db.commit()
            self.logger.info(f"Imported {imported} new trades from blockchain")
            
            return imported
            
        except Exception as e:
            self.logger.error(f"Failed to import blockchain history: {e}", exc_info=True)
            self.db.rollback()
            raise

    async def sync_current_positions(self) -> SyncResult:
        """
        Fetch current open positions from blockchain.

        Compares with DB. Marks positions as closed if blockchain says they're gone.
        Updates last_sync_at timestamps for positions still open.

        Returns:
            SyncResult with updated/closed counts
        """
        self.logger.info("Syncing current positions from blockchain")
        
        result = SyncResult()
        
        try:
            # Fetch open positions from CLOB API
            blockchain_positions = await self._fetch_open_positions()
            
            # Build map of blockchain positions by market_id
            blockchain_map = {
                pos["asset_id"]: pos
                for pos in blockchain_positions
            }
            
            self.logger.debug(f"Blockchain has {len(blockchain_map)} open positions")
            
            # Query DB for open trades
            db_open_trades = self.db.query(Trade).filter(
                (Trade.trading_mode == self.mode) &
                (Trade.settlement_time.is_(None)) &  # Still open
                (Trade.settled == False)
            ).all()
            
            self.logger.debug(f"DB has {len(db_open_trades)} open trades")
            
            # Compare
            for db_trade in db_open_trades:
                if db_trade.market_ticker not in blockchain_map:
                    # Blockchain says position is closed but DB says open
                    # Mark as closed with settlement_source='clob_api'
                    self.logger.warning(
                        f"Position {db_trade.market_ticker} (id={db_trade.id}) "
                        f"closed on-chain but open in DB. Marking as closed."
                    )
                    db_trade.settlement_time = datetime.now(timezone.utc)
                    db_trade.settlement_source = "clob_api"
                    db_trade.blockchain_verified = True
                    db_trade.settled = True
                    db_trade.result = "closed"
                    result.closed_count += 1
                else:
                    # Position still open - update fields
                    blockchain_pos = blockchain_map[db_trade.market_ticker]
                    db_trade.last_sync_at = datetime.now(timezone.utc)
                    db_trade.blockchain_verified = True
                    result.updated_count += 1
                    self.logger.debug(
                        f"Position {db_trade.market_ticker} (id={db_trade.id}) "
                        f"still open, updated sync timestamp"
                    )
            
            self.db.commit()
            self.logger.info(
                f"Position sync: {result.updated_count} updated, {result.closed_count} closed"
            )
            
        except Exception as e:
            error_msg = f"Failed to sync current positions: {e}"
            self.logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)
            self.db.rollback()
        
        return result

    async def detect_orphaned_positions(self) -> list[OrphanedPosition]:
        """
        Find positions on blockchain that don't exist in DB.

        These are trades placed by bot but DB record was lost (or external trades).

        Returns:
            List of OrphanedPosition objects
        """
        self.logger.info("Detecting orphaned positions")
        
        try:
            blockchain_positions = await self._fetch_open_positions()
            
            orphans = []
            for pos in blockchain_positions:
                # Check if trade exists in DB
                existing = self.db.query(Trade).filter(
                    (Trade.market_ticker == pos["asset_id"]) &
                    (Trade.trading_mode == self.mode) &
                    (Trade.settled == False)
                ).first()
                
                if existing:
                    continue  # Found in DB
                
                # Orphaned!
                orphan = OrphanedPosition(
                    market_id=pos["asset_id"],
                    blockchain_size=pos["size"],
                    blockchain_entry_price=pos["avg_price"],
                    clob_order_id=pos.get("order_id"),
                    detected_at=datetime.now(timezone.utc)
                )
                orphans.append(orphan)
                self.logger.warning(
                    f"Orphaned position detected: {orphan.market_id} "
                    f"({orphan.blockchain_size} shares @ {orphan.blockchain_entry_price})"
                )
            
            self.logger.info(f"Found {len(orphans)} orphaned positions")
            return orphans
            
        except Exception as e:
            self.logger.error(f"Failed to detect orphaned positions: {e}", exc_info=True)
            return []

    async def close_orphaned_position(self, orphan: OrphanedPosition) -> bool:
        """
        Create a Trade record for orphaned position so it's tracked.

        Sets source='orphaned' and blockchain_verified=True.

        Args:
            orphan: OrphanedPosition to create DB record for

        Returns:
            True if successfully created, False if already exists
        """
        self.logger.info(f"Creating DB record for orphaned position: {orphan.market_id}")
        
        try:
            # Check again if it exists (race condition)
            existing = self.db.query(Trade).filter(
                (Trade.market_ticker == orphan.market_id) &
                (Trade.trading_mode == self.mode)
            ).first()
            
            if existing:
                self.logger.debug(f"Orphan {orphan.market_id} already has DB record (id={existing.id})")
                return False
            
            # Create trade record
            trade = Trade(
                market_ticker=orphan.market_id,
                platform="polymarket",
                direction="up",  # Default to "up" - we don't know actual direction from position alone
                entry_price=orphan.blockchain_entry_price,
                size=orphan.blockchain_size,
                timestamp=orphan.detected_at,
                trading_mode=self.mode,
                
                # Reconciliation fields (Task 1)
                source="orphaned",                    # Position found on-chain, reconstructed
                clob_order_id=orphan.clob_order_id,
                blockchain_verified=True,
                settlement_source="clob_api",
                external_import_at=orphan.detected_at,
                
                # Default values for required fields
                model_probability=0.5,  # Unknown for orphaned positions
                market_price_at_entry=orphan.blockchain_entry_price,
                edge_at_entry=0.0,  # Unknown for orphaned positions
            )
            
            self.db.add(trade)
            self.db.commit()
            
            self.logger.info(f"Created orphaned position record: id={trade.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to close orphaned position: {e}", exc_info=True)
            self.db.rollback()
            return False

    async def _fetch_open_positions(self) -> list[dict]:
        """
        Fetch trader's current open positions from CLOB API.

        Called by sync_current_positions() and detect_orphaned_positions().

        Returns:
            List of position dicts with structure:
            [
                {
                    "asset_id": "0x123abc...",
                    "order_id": "0xorder123",
                    "size": 100.5,
                    "avg_price": 0.42,
                    "outcome": "YES",
                    "timestamp": "2025-04-17T10:30:00Z"
                },
                ...
            ]
        """
        self.logger.info(f"Fetching open positions for {self.wallet_address}")
        
        try:
            # Call CLOB API's get_trader_positions() endpoint
            # Signature: get_trader_positions(trader_address: str) -> List[Dict]
            positions = await self.clob.get_trader_positions(
                wallet=self.wallet_address
            )
            
            # Filter to only open positions (size > 0)
            open_positions = [
                pos for pos in positions 
                if pos.get("size", 0) > 0 and pos.get("exit_timestamp") is None
            ]
            
            self.logger.debug(f"Found {len(open_positions)} open positions")
            return open_positions
        
        except Exception as e:
            self.logger.error(f"Failed to fetch open positions: {e}", exc_info=True)
            # Return empty list on error (graceful degradation)
            # Caller will handle empty list as "no positions"
            return []
