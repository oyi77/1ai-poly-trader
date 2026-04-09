"""Trade settlement logic for BTC 5-min and weather markets using Polymarket API.

This module provides the main settlement orchestration functions.
Helper functions for API resolution, P&L calculation, and weather calibration
are in settlement_helpers.py.
"""
import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session

from backend.models.database import Trade, BotState

from backend.core.settlement_helpers import (
    fetch_polymarket_resolution,
    calculate_pnl,
    _resolve_markets,
    process_settled_trade,
)

logger = logging.getLogger("trading_bot")


async def settle_pending_trades(db: Session) -> List[Trade]:
    """
    Process all pending trades for settlement.
    Uses REAL market outcomes from Polymarket API.
    Deduplicates API calls: each unique market_ticker is resolved once.
    """
    try:
        pending = db.query(Trade).filter(Trade.settled == False).all()  # noqa: E712
    except Exception as e:
        logger.error(f"Failed to query pending trades: {e}")
        return []

    if not pending:
        logger.info("No pending trades to settle")
        return []

    # Mark stale trades (unsettled for >7 days) as expired
    from datetime import timedelta

    now = datetime.utcnow()
    stale_threshold = now - timedelta(days=7)

    expired_count = 0
    for trade in pending:
        if trade.timestamp and trade.timestamp < stale_threshold:
            trade.settled = True
            trade.result = "expired"
            trade.settlement_time = now
            expired_count += 1

    if expired_count > 0:
        db.commit()
        logger.info(f"Marked {expired_count} stale trades as expired")

    # Separate weather vs normal trades and collect unique tickers
    normal_tickers: set = set()
    weather_tickers: set = set()
    trade_slugs: dict = {}
    trade_platforms: dict = {}

    for trade in pending:
        market_type = getattr(trade, "market_type", "btc") or "btc"
        ticker = trade.market_ticker
        trade_slugs[ticker] = getattr(trade, "event_slug", None)
        trade_platforms[ticker] = (
            getattr(trade, "platform", "polymarket") or "polymarket"
        )
        if market_type == "weather":
            weather_tickers.add(ticker)
        else:
            normal_tickers.add(ticker)

    unique_tickers = normal_tickers | weather_tickers
    logger.info(
        f"Settlement: {len(pending)} trades across {len(unique_tickers)} markets "
        f"(saved {len(pending) - len(unique_tickers)} API calls)"
    )

    resolutions = await _resolve_markets(
        normal_tickers, weather_tickers, trade_slugs, trade_platforms
    )

    def _settlement_from_resolution(trade) -> tuple:
        ticker = trade.market_ticker
        if ticker not in resolutions:
            return False, None, None
        is_resolved, settlement_value = resolutions[ticker]
        if not is_resolved or settlement_value is None:
            return False, None, None
        pnl = calculate_pnl(trade, settlement_value)
        market_type = getattr(trade, "market_type", "btc") or "btc"
        if market_type != "weather":
            mapped_dir = "UP" if trade.direction in ("up", "yes") else "DOWN"
            outcome = "UP" if settlement_value == 1.0 else "DOWN"
            result = "WIN" if mapped_dir == outcome else "LOSS"
            logger.info(
                f"Trade {trade.id} settled: {mapped_dir} @ {trade.entry_price:.0%} -> "
                f"{result} P&L: ${pnl:+.2f}"
            )
        return True, settlement_value, pnl

    results = [(t, _settlement_from_resolution(t)) for t in pending]

    settled_trades = []
    for item in results:
        if isinstance(item, Exception):
            logger.error(f"Settlement error: {item}")
            continue
        trade, (is_settled, settlement_value, pnl) = item
        if process_settled_trade(trade, is_settled, settlement_value, pnl, db):
            settled_trades.append(trade)

    if settled_trades:
        try:
            db.commit()
            logger.info(f"Settled {len(settled_trades)} trades")
        except Exception as e:
            logger.error(f"Failed to commit settlements: {e}")
            db.rollback()
            return []
    else:
        logger.info("No trades ready for settlement (markets still open)")

    return settled_trades


async def update_bot_state_with_settlements(
    db: Session, settled_trades: List[Trade]
) -> None:
    """Update bot state with P&L from settled trades."""
    if not settled_trades:
        return

    try:
        state = db.query(BotState).first()
        if not state:
            logger.warning("Bot state not found")
            return

        for trade in settled_trades:
            if trade.pnl is not None:
                trading_mode = getattr(trade, "trading_mode", "paper") or "paper"

                # Always update mode-specific stats
                if trading_mode == "paper":
                    state.paper_pnl = (state.paper_pnl or 0.0) + trade.pnl
                    state.paper_bankroll = (state.paper_bankroll or 10000.0) + trade.pnl
                    state.paper_trades = (state.paper_trades or 0) + 1
                    if trade.result == "win":
                        state.paper_wins = (state.paper_wins or 0) + 1
                else:
                    state.total_pnl = (state.total_pnl or 0.0) + trade.pnl
                    state.bankroll = (state.bankroll or 0.0) + trade.pnl
                    if trade.result == "win":
                        state.winning_trades = (state.winning_trades or 0) + 1
                    state.total_trades = (state.total_trades or 0) + 1

                # Also update general stats for paper mode so dashboard shows correctly
                if trading_mode == "paper":
                    state.total_pnl = (state.total_pnl or 0.0) + trade.pnl
                    state.bankroll = (state.bankroll or 0.0) + trade.pnl
                    state.total_trades = (state.total_trades or 0) + 1
                    if trade.result == "win":
                        state.winning_trades = (state.winning_trades or 0) + 1

        db.commit()
        logger.info(
            f"Updated bot state: Bankroll ${state.bankroll:.2f}, P&L ${state.total_pnl:+.2f}"
        )
    except Exception as e:
        logger.error(f"Failed to update bot state: {e}")
        db.rollback()
