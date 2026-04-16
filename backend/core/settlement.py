"""Trade settlement logic using Polymarket API. Helpers live in settlement_helpers.py."""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.database import Trade, BotState

from backend.core.settlement_helpers import (
    fetch_polymarket_resolution,
    calculate_pnl,
    _resolve_markets,
    _parse_market_resolution,
    check_market_settlement,
    process_settled_trade,
)

logger = logging.getLogger("trading_bot")

# Prevent concurrent settlement runs from double-applying PnL
_settlement_lock = asyncio.Lock()


async def settle_pending_trades(db: Session) -> List[Trade]:
    """Settle all pending trades using Polymarket API outcomes. Deduplicates API calls per ticker."""
    if _settlement_lock.locked():
        logger.info("Settlement already in progress, skipping")
        return []

    async with _settlement_lock:
        try:
            pending = db.query(Trade).filter(Trade.settled.is_(False)).all()
        except Exception as e:
            logger.error(f"Failed to query pending trades: {e}")
            return []

        if not pending:
            logger.info("No pending trades to settle")
            return []

        now = datetime.now(timezone.utc)
        stale_threshold = now - timedelta(hours=settings.STALE_TRADE_HOURS)

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

        # Resolve ALL markets before expiring stale trades — a stale trade
        # whose market already resolved must get proper PnL, not pnl=0.
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

        settled_trades = []

        for trade in pending:
            is_settled, settlement_value, pnl = _settlement_from_resolution(trade)
            if await process_settled_trade(
                trade, is_settled, settlement_value, pnl, db
            ):
                settled_trades.append(trade)
                continue

            # Check if market's end_date has passed - if so and API can't
            # resolve it, expire immediately instead of waiting 48 hours.
            market_end = trade.market_end_date
            if market_end:
                if market_end.tzinfo is None:
                    market_end = market_end.replace(tzinfo=timezone.utc)
                if market_end < now:
                    # Market expired and API couldn't resolve - expire now
                    trade.settled = True
                    trade.result = "expired"
                    trade.settlement_time = now
                    trade.pnl = 0
                    settled_trades.append(trade)
                    logger.info(
                        f"Trade {trade.id} expired: market end_date {market_end.isoformat()} passed"
                    )
                    continue

            ts = trade.timestamp
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts and ts < stale_threshold:
                # Last-chance individual resolution check before expiring.
                # The batch resolution above may have missed this market due to
                # transient API errors, caching, or timing. One final direct
                # call can recover trades that would otherwise expire at pnl=0.
                try:
                    is_resolved_retry, sv_retry = await fetch_polymarket_resolution(
                        trade.market_ticker,
                        event_slug=getattr(trade, "event_slug", None),
                    )
                    if is_resolved_retry and sv_retry is not None:
                        pnl_retry = calculate_pnl(trade, sv_retry)
                        if await process_settled_trade(
                            trade, True, sv_retry, pnl_retry, db
                        ):
                            logger.info(
                                f"Trade {trade.id} rescued from expiry via retry: pnl=${pnl_retry:+.2f}"
                            )
                            settled_trades.append(trade)
                            continue
                except Exception as e:
                    logger.debug(
                        f"Last-chance resolution retry failed for trade {trade.id}: {e}"
                    )

                trade.settled = True
                trade.result = "expired"
                trade.settlement_time = now
                trade.pnl = 0
                settled_trades.append(trade)

        expired_count = sum(1 for t in settled_trades if t.result == "expired")
        resolved_count = len(settled_trades) - expired_count
        if resolved_count:
            logger.info(f"Settled {resolved_count} trades with market resolution")
        if expired_count:
            logger.info(f"Marked {expired_count} stale trades as expired")
        if not settled_trades:
            logger.info("No trades ready for settlement (markets still open)")

        # Commit trade settlement state to DB so it persists even if
        # update_bot_state_with_settlements() fails or is never called.
        if settled_trades:
            try:
                db.commit()
            except Exception as e:
                logger.error(f"Failed to commit trade settlements: {e}")
                db.rollback()

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
            if trade.pnl is None:
                continue

            trading_mode = getattr(trade, "trading_mode", "paper") or "paper"
            is_real_trade = trade.result in ("win", "loss")
            is_expired_or_push = trade.result in ("expired", "push")

            if trading_mode == "paper":
                if is_real_trade:
                    # Win/loss: return the original stake AND apply net PNL.
                    # At trade open, bankroll was reduced by trade.size.
                    # trade.pnl is net profit (positive for win, -size for loss).
                    # So gross return = trade.size + trade.pnl:
                    #   WIN:  size + ((size/entry_price) - size) = size/entry_price
                    #   LOSS: size + (-size) = 0  (stake already deducted at open)
                    state.paper_pnl = (state.paper_pnl or 0.0) + trade.pnl
                    state.paper_bankroll = (
                        (
                            state.paper_bankroll
                            if state.paper_bankroll is not None
                            else settings.INITIAL_BANKROLL
                        )
                        + trade.size
                        + trade.pnl
                    )
                    state.paper_trades = (state.paper_trades or 0) + 1
                    if trade.result == "win":
                        state.paper_wins = (state.paper_wins or 0) + 1
                elif is_expired_or_push:
                    # Expired/push: return stake to bankroll but do NOT
                    # count as a trade and do NOT affect realized PNL.
                    state.paper_bankroll = (
                        state.paper_bankroll
                        if state.paper_bankroll is not None
                        else settings.INITIAL_BANKROLL
                    ) + trade.size
                    logger.info(
                        f"Expired/push trade {trade.id}: returned ${trade.size:.2f} to paper bankroll"
                    )
            elif trading_mode == "testnet":
                if is_real_trade:
                    state.testnet_pnl = (state.testnet_pnl or 0.0) + trade.pnl
                    state.testnet_bankroll = (
                        (state.testnet_bankroll or 0.0) + trade.size + trade.pnl
                    )
                    state.testnet_trades = (state.testnet_trades or 0) + 1
                    if trade.result == "win":
                        state.testnet_wins = (state.testnet_wins or 0) + 1
                elif is_expired_or_push:
                    state.testnet_bankroll = (
                        state.testnet_bankroll or 0.0
                    ) + trade.size
                    logger.info(
                        f"Expired/push trade {trade.id}: returned ${trade.size:.2f} to testnet bankroll"
                    )
            else:  # live mode — isolated from testnet
                if is_real_trade:
                    state.total_pnl = (state.total_pnl or 0.0) + trade.pnl
                    # Do NOT modify state.bankroll for live mode —
                    # wallet_sync_job updates it from the real CLOB balance.
                    state.total_trades = (state.total_trades or 0) + 1
                    if trade.result == "win":
                        state.winning_trades = (state.winning_trades or 0) + 1
                elif is_expired_or_push:
                    # No bankroll modification — CLOB balance is authoritative for live mode.
                    pass

            # AGI hook: update Bayesian Kelly posterior on each trade outcome
            if is_real_trade:
                try:
                    from backend.agents.pipeline import AGITradingPipeline

                    _agi = AGITradingPipeline()
                    _agi.record_outcome(
                        market_ticker=trade.market_ticker,
                        won=(trade.result == "win"),
                    )
                except Exception as _e:
                    logger.debug(f"[settlement] AGI record_outcome skipped: {_e}")

        try:
            db.commit()
        except Exception as e:
            logger.error(f"Failed to commit settlement + bot state: {e}")
            db.rollback()
            return

        # Log stats for ALL modes that had settlements
        modes_with_settlements = set(
            getattr(t, "trading_mode", "paper") or "paper"
            for t in settled_trades
            if t.pnl is not None
        )
        for m in sorted(modes_with_settlements):
            if m == "paper":
                logger.info(
                    f"Updated bot state (paper): Bankroll ${state.paper_bankroll:.2f}, "
                    f"P&L ${state.paper_pnl:+.2f}, {state.paper_trades} trades"
                )
            elif m == "testnet":
                logger.info(
                    f"Updated bot state (testnet): Bankroll ${state.testnet_bankroll:.2f}, "
                    f"P&L ${state.testnet_pnl:+.2f}, {state.testnet_trades} trades"
                )
            else:
                logger.info(
                    f"Updated bot state (live): Bankroll ${state.bankroll:.2f}, "
                    f"P&L ${state.total_pnl:+.2f}, {state.total_trades} trades"
                )
    except Exception as e:
        logger.error(f"Failed to update bot state: {e}")
        db.rollback()


async def reconcile_bot_state(db: Session) -> None:
    """Recalculate bot_state from trade history to prevent drift."""
    try:
        from sqlalchemy import func, case

        state = db.query(BotState).first()
        if not state:
            return

        for mode in ("paper", "testnet", "live"):
            real_trades = (
                db.query(
                    func.count(Trade.id),
                    func.sum(Trade.pnl),
                    func.sum(case((Trade.result == "win", 1), else_=0)),
                )
                .filter(
                    Trade.settled.is_(True),
                    Trade.trading_mode == mode,
                    Trade.result.in_(("win", "loss")),
                )
                .first()
            )

            trade_count, realized_pnl, win_count = real_trades
            trade_count = trade_count or 0
            realized_pnl = round(realized_pnl or 0.0, 2)
            win_count = win_count or 0

            open_exposure = (
                db.query(func.sum(Trade.size))
                .filter(Trade.settled.is_(False), Trade.trading_mode == mode)
                .scalar()
            ) or 0.0

            if mode == "paper":
                drift_bankroll = abs(
                    (state.paper_bankroll or 0)
                    - (settings.INITIAL_BANKROLL + realized_pnl - open_exposure)
                )
                drift_pnl = abs((state.paper_pnl or 0) - realized_pnl)
                if drift_bankroll > 0.01 or drift_pnl > 0.01:
                    logger.warning(
                        f"Bot state drift detected (paper)! "
                        f"Bankroll Δ${drift_bankroll:.2f}, PNL Δ${drift_pnl:.2f}"
                    )
                    state.paper_bankroll = round(
                        settings.INITIAL_BANKROLL + realized_pnl - open_exposure, 2
                    )
                    state.paper_pnl = realized_pnl
                    state.paper_trades = trade_count
                    state.paper_wins = win_count
                    logger.info("Bot state reconciled from trade history (paper)")
            elif mode == "testnet":
                drift_bankroll = abs(
                    (state.testnet_bankroll or 0)
                    - (settings.INITIAL_BANKROLL + realized_pnl - open_exposure)
                )
                drift_pnl = abs((state.testnet_pnl or 0) - realized_pnl)
                if drift_bankroll > 0.01 or drift_pnl > 0.01:
                    logger.warning(
                        f"Bot state drift detected (testnet)! "
                        f"Bankroll Δ${drift_bankroll:.2f}, PNL Δ${drift_pnl:.2f}"
                    )
                    state.testnet_bankroll = round(
                        settings.INITIAL_BANKROLL + realized_pnl - open_exposure, 2
                    )
                    state.testnet_pnl = realized_pnl
                    state.testnet_trades = trade_count
                    state.testnet_wins = win_count
                    logger.info("Bot state reconciled from trade history (testnet)")
            else:
                drift_pnl = abs((state.total_pnl or 0) - realized_pnl)
                if drift_pnl > 0.01:
                    logger.warning(
                        f"Bot state drift detected (live)! PNL Δ${drift_pnl:.2f}"
                    )
                    state.total_pnl = realized_pnl
                    state.total_trades = trade_count
                    state.winning_trades = win_count
                    logger.info("Bot state reconciled from trade history (live)")

        db.commit()
        logger.debug("Bot state reconciliation complete")

    except Exception as e:
        logger.error(f"Bot state reconciliation failed: {e}")
        db.rollback()
