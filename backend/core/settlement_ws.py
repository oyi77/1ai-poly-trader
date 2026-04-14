"""
Real-time settlement handler using Polymarket WebSocket market_resolved events.

When Polymarket resolves a market, we receive the event via WebSocket and can
settle trades immediately instead of waiting for the next settlement cycle.
"""

import asyncio
import logging
from typing import Optional

from backend.data.ws_client import CLOBWebSocket, SettlementEvent
from backend.models.database import SessionLocal, Trade

logger = logging.getLogger("trading_bot")


class SettlementWebSocketHandler:
    """
    Listens to Polymarket WebSocket for market_resolved events and settles
    trades in real-time.

    Usage:
        handler = SettlementWebSocketHandler()
        await handler.start()
        # ... handler runs in background ...
        await handler.stop()
    """

    def __init__(self):
        self._ws: Optional[CLOBWebSocket] = None
        self._running = False
        self._token_id_to_ticker: dict[str, str] = {}

    async def start(self) -> None:
        """Start the settlement WebSocket listener."""
        self._running = True
        await self._load_subscriptions()
        self._ws = CLOBWebSocket(
            on_settlement=self._handle_settlement,
        )
        asyncio.create_task(self._ws.run())
        logger.info("[SettlementWS] Started settlement WebSocket handler")

    async def stop(self) -> None:
        """Stop the settlement WebSocket listener."""
        self._running = False
        if self._ws:
            await self._ws.stop()
        logger.info("[SettlementWS] Stopped settlement WebSocket handler")

    async def _load_subscriptions(self) -> None:
        """Load all open trade token_ids to subscribe to."""
        db = SessionLocal()
        try:
            trades = db.query(Trade).filter(Trade.settled == False).all()
            for trade in trades:
                if hasattr(trade, "token_id") and trade.token_id:
                    self._token_id_to_ticker[trade.token_id] = trade.market_ticker
                elif trade.market_ticker:
                    self._token_id_to_ticker[trade.market_ticker] = trade.market_ticker
            logger.info(
                f"[SettlementWS] Subscribing to {len(self._token_id_to_ticker)} open markets"
            )
        finally:
            db.close()

    def subscribe_to_market(self, token_id: str, market_ticker: str) -> None:
        """Subscribe to a new market's settlement events."""
        self._token_id_to_ticker[token_id] = market_ticker
        if self._ws and self._ws.is_connected:
            asyncio.create_task(self._ws.subscribe(token_id))

    def _handle_settlement(self, event: SettlementEvent) -> None:
        """Handle a market_resolved event from WebSocket."""
        logger.info(
            f"[SettlementWS] Market resolved: token_id={event.token_id}, "
            f"outcome={event.outcome}, market={event.market_address}"
        )

        # Map token_id to market_ticker
        ticker = self._token_id_to_ticker.get(event.token_id, event.token_id)

        # Schedule the settlement to run in async context
        asyncio.create_task(self._settle_trade(event.token_id, ticker, event.outcome))

    async def _settle_trade(
        self, token_id: str, market_ticker: str, outcome: str
    ) -> None:
        """Settle all open trades for a market."""
        db = SessionLocal()
        try:
            trades = (
                db.query(Trade)
                .filter(Trade.settled == False)
                .filter(
                    (Trade.market_ticker == market_ticker)
                    | (Trade.market_ticker == token_id)
                )
                .all()
            )

            if not trades:
                logger.debug(f"[SettlementWS] No open trades found for {market_ticker}")
                return

            # Parse outcome: "YES" or "NO", convert to settlement value
            settlement_value = 1.0 if outcome.upper() in ("YES", "UP") else 0.0

            from backend.core.settlement_helpers import (
                calculate_pnl,
                process_settled_trade,
            )

            settled_count = 0
            for trade in trades:
                pnl = calculate_pnl(trade, settlement_value)
                if await process_settled_trade(trade, True, settlement_value, pnl, db):
                    settled_count += 1
                    logger.info(
                        f"[SettlementWS] Settled trade {trade.id}: "
                        f"{trade.direction} @ {trade.entry_price:.0%} -> "
                        f"{'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'PUSH'} "
                        f"P&L: ${pnl:+.2f}"
                    )

            if settled_count > 0:
                db.commit()
                logger.info(
                    f"[SettlementWS] Settled {settled_count} trades for {market_ticker}"
                )

        except Exception as e:
            logger.error(
                f"[SettlementWS] Error settling trades for {market_ticker}: {e}",
                exc_info=True,
            )
            db.rollback()
        finally:
            db.close()


# Global handler instance
_settlement_handler: Optional[SettlementWebSocketHandler] = None


async def get_settlement_handler() -> SettlementWebSocketHandler:
    """Get or create the global settlement WebSocket handler."""
    global _settlement_handler
    if _settlement_handler is None:
        _settlement_handler = SettlementWebSocketHandler()
        await _settlement_handler.start()
    return _settlement_handler


async def stop_settlement_handler() -> None:
    """Stop the global settlement WebSocket handler."""
    global _settlement_handler
    if _settlement_handler is not None:
        await _settlement_handler.stop()
        _settlement_handler = None
