"""Trade settlement logic using Polymarket API. Helpers live in settlement_helpers.py."""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List
from sqlalchemy.orm import Session

import re as _re

from backend.config import settings
from backend.models.database import Trade, BotState
from backend.core.alert_manager import AlertManager

from backend.core.settlement_helpers import (
    fetch_resolution_for_trade,
    check_market_settlement as check_market_settlement,
    calculate_pnl,
    _parse_market_resolution as _parse_market_resolution,
    _resolve_markets,
    process_settled_trade,
)

logger = logging.getLogger("trading_bot")

_settlement_lock = asyncio.Lock()


async def _fetch_pm_portfolio_value() -> float | None:
    """Fetch live total equity (USDC cash + open position value)."""
    from backend.core.bankroll_reconciliation import fetch_pm_total_equity

    return await fetch_pm_total_equity()


async def _settle_btc_5min_trade(trade: Trade, now: datetime) -> Trade | None:
    """Settle a BTC 5-min UP/DOWN market trade whose window has expired."""
    ticker = trade.market_ticker or ""
    match = _re.search(r"btc-updown-5m-(\d+)", ticker)
    if not match:
        return None

    window_end = datetime.fromtimestamp(int(match.group(1)) + 300, tz=timezone.utc)

    if now < window_end:
        return None

    try:
        from backend.data.btc_markets import fetch_btc_market_for_settlement
        btc_market = await fetch_btc_market_for_settlement(ticker)
        if btc_market and btc_market.closed:
            entry_price = float(trade.entry_price or 0)
            size = float(trade.size or 0)
            direction = (trade.direction or "up").lower()

            if direction == "up":
                won = btc_market.up_price > 0.9
            elif direction == "down":
                won = btc_market.down_price > 0.9
            else:
                won = False

            if won:
                trade.result = "win"
                # Win: each share pays $1; shares = size/entry_price
                # PnL = shares - cost = (size/entry_price) - size
                trade.pnl = (size / entry_price) - size if entry_price > 0 else 0.0
                trade.settlement_value = size / entry_price if entry_price > 0 else 0.0
            else:
                trade.result = "loss"
                # Loss: entire investment lost
                trade.pnl = -size
                trade.settlement_value = 0.0

            trade.settled = True
            trade.settlement_time = now
            trade.settlement_source = "btc_5min_auto"
            return trade
    except Exception as e:
        logger.debug(f"btc_5min settlement fetch failed for {ticker}: {e}")

    trade.settled = True
    trade.result = "push"
    trade.pnl = 0.0
    trade.settlement_time = now
    trade.settlement_source = "btc_5min_auto_breakeven"
    trade.settlement_value = float(trade.size or 0)
    return trade


async def settle_pending_trades(db: Session) -> List[Trade]:
    """Settle all pending trades using Polymarket API outcomes. Deduplicates API calls per ticker."""
    if _settlement_lock.locked():
        logger.info("Settlement already in progress, skipping")
        return []

    async with _settlement_lock:
        alert_manager = AlertManager(db)
        
        try:
            from backend.core.settlement_helpers import reconcile_positions

            trades_to_close = await reconcile_positions(db)

            if trades_to_close:
                now = datetime.now(timezone.utc)
                closed_count = 0

                for trade_id in trades_to_close:
                    trade = db.query(Trade).filter(Trade.id == trade_id).first()
                    if trade and not trade.settled:
                        is_resolved, settlement_value = await fetch_resolution_for_trade(trade)
                        
                        if is_resolved and settlement_value is not None:
                            pnl = calculate_pnl(trade, settlement_value)
                            await process_settled_trade(
                                trade, True, settlement_value, pnl, db
                            )
                            logger.info(
                                f"Position reconciliation: trade {trade.id} settled with resolution (pnl=${pnl:+.2f})"
                            )
                        else:
                            trade.settled = True
                            trade.result = "loss"
                            trade.settlement_time = now
                            trade.pnl = -float(trade.size or 0)
                            trade.settlement_value = 0.0
                            trade.settlement_source = "closed_unresolved"
                            logger.info(
                                f"Position reconciliation: trade {trade.id} closed without resolution (assumed loss, pnl=${trade.pnl:+.2f})"
                            )
                        
                        closed_count += 1

                        try:
                            from backend.core.event_bus import _broadcast_event

                            _broadcast_event(
                                "trade_settled",
                                {
                                    "trade_id": trade.id,
                                    "market_ticker": trade.market_ticker,
                                    "result": trade.result,
                                    "pnl": trade.pnl or 0.0,
                                    "mode": getattr(trade, "trading_mode", "paper"),
                                },
                            )
                        except Exception as e:
                            logger.debug(f"Broadcast event failed: {e}")

                if closed_count > 0:
                    db.commit()
                    logger.info(
                        f"Position reconciliation: processed {closed_count} trades"
                    )
        except Exception as e:
            logger.error(f"Position reconciliation failed: {e}", exc_info=True)
            alert_manager.check_failed_settlement(
                trade_id=0,
                reason=f"Position reconciliation failed: {e}",
                mode=settings.TRADING_MODE,
            )

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

            # BTC 5-min UP/DOWN market settlement (btc-updown-5m-* tickers)
            if not is_settled and trade.market_ticker and trade.market_ticker.startswith("btc-updown-5m-"):
                btc_result = await _settle_btc_5min_trade(trade, now)
                if btc_result:
                    settled_trades.append(btc_result)
                    continue

            if await process_settled_trade(
                trade, is_settled, settlement_value, pnl, db
            ):
                from backend.models.audit_logger import log_settlement_completed
                log_settlement_completed(
                    db=db,
                    trade_id=trade.id,
                    old_state={
                        "settled": False,
                        "result": "pending",
                        "pnl": None,
                    },
                    new_state={
                        "settled": True,
                        "result": trade.result,
                        "pnl": trade.pnl,
                        "settlement_value": settlement_value,
                        "settlement_time": trade.settlement_time.isoformat() if trade.settlement_time else None,
                    },
                    user_id="system:settlement",
                )
                settled_trades.append(trade)
                continue

            # Check if market's end_date has passed - if so and API can't
            # resolve it, expire immediately instead of waiting 48 hours.
            market_end = trade.market_end_date
            if market_end:
                if market_end.tzinfo is None:
                    market_end = market_end.replace(tzinfo=timezone.utc)
                if market_end < now:
                    # Market expired and API couldn't resolve — assume loss
                    trade.settled = True
                    trade.result = "loss"
                    trade.settlement_time = now
                    trade.pnl = -float(trade.size or 0)
                    trade.settlement_value = 0.0
                    trade.settlement_source = "expired_unresolved"
                    settled_trades.append(trade)
                    logger.info(
                        f"Trade {trade.id} expired: market end_date {market_end.isoformat()} passed (assumed loss)"
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
                    is_resolved_retry, sv_retry = await fetch_resolution_for_trade(trade)
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
                trade.result = "loss"
                trade.settlement_time = now
                trade.pnl = -float(trade.size or 0)
                trade.settlement_value = 0.0
                trade.settlement_source = "stale_expired"
                settled_trades.append(trade)

        unresolved_count = sum(
            1 for t in settled_trades
            if getattr(t, "settlement_source", None) in (
                "expired_unresolved", "closed_unresolved", "stale_expired"
            )
        )
        resolved_count = len(settled_trades) - unresolved_count
        if resolved_count:
            logger.info(f"Settled {resolved_count} trades with market resolution")
        if unresolved_count:
            logger.info(f"Marked {unresolved_count} unresolvable trades as total losses")
        if not settled_trades:
            logger.info("No trades ready for settlement (markets still open)")

        # Commit trade settlement state to DB so it persists even if
        # update_bot_state_with_settlements() fails or is never called.
        if settled_trades:
            try:
                db.commit()
            except Exception as e:
                logger.error(f"Failed to commit trade settlements: {e}")
                alert_manager.check_failed_settlement(
                    trade_id=0,
                    reason=f"Failed to commit settlements: {e}",
                    mode=settings.TRADING_MODE,
                )
                db.rollback()

        return settled_trades


async def update_bot_state_with_settlements(
    db: Session, settled_trades: List[Trade]
) -> None:
    """Update bot state with P&L from settled trades."""
    if not settled_trades:
        return

    try:
        for trade in settled_trades:
            if trade.pnl is None:
                continue

            trading_mode = getattr(trade, "trading_mode", "paper") or "paper"
            is_real_trade = trade.result in ("win", "loss")
            is_expired_or_push = trade.result in ("expired", "push", "closed")

            # Route updates to mode-specific fields
            if trading_mode == "paper":
                state = db.query(BotState).filter_by(mode=trading_mode).first()
                if not state:
                    logger.warning(f"Bot state not found for mode {trading_mode}")
                    continue
                if is_real_trade:
                    state.paper_pnl = (state.paper_pnl or 0.0) + trade.pnl
                    state.paper_bankroll = max(
                        0.0, (state.paper_bankroll or 0.0) + trade.size + trade.pnl
                    )
                    state.paper_trades = (state.paper_trades or 0) + 1
                    if trade.result == "win":
                        state.paper_wins = (state.paper_wins or 0) + 1
                elif is_expired_or_push:
                    state.paper_bankroll = (state.paper_bankroll or 0.0) + trade.size
                    logger.info(
                        f"Expired/push trade {trade.id}: returned ${trade.size:.2f} to paper bankroll"
                    )
            elif trading_mode == "testnet":
                state = db.query(BotState).filter_by(mode=trading_mode).first()
                if not state:
                    logger.warning(f"Bot state not found for mode {trading_mode}")
                    continue
                if is_real_trade:
                    state.testnet_pnl = (state.testnet_pnl or 0.0) + trade.pnl
                    state.testnet_bankroll = max(
                        0.0, (state.testnet_bankroll or 0.0) + trade.size + trade.pnl
                    )
                    state.testnet_trades = (state.testnet_trades or 0) + 1
                    if trade.result == "win":
                        state.testnet_wins = (state.testnet_wins or 0) + 1
                elif is_expired_or_push:
                    state.testnet_bankroll = (state.testnet_bankroll or 0.0) + trade.size
                    logger.info(
                        f"Expired/push trade {trade.id}: returned ${trade.size:.2f} to testnet bankroll"
                    )
            else:
                # Live BotState financial fields are derived from external account
                # equity, not local trade ledger P&L.  Do not mutate live state in
                # this transaction; reconcile from CLOB cash + PM open positions
                # after settlement rows are committed.
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

        modes_with_settlements = {
            getattr(t, "trading_mode", "paper") or "paper"
            for t in settled_trades
            if t.pnl is not None
        }

        # Sync live bankroll from authoritative total equity source.
        if "live" in modes_with_settlements:
            try:
                from backend.core.bankroll_reconciliation import reconcile_bot_state as _reconcile

                reports = await _reconcile(
                    db,
                    modes=("live",),
                    apply=True,
                    commit=True,
                    source="settlement_live_sync",
                )
                if reports:
                    report = reports[0]
                    logger.info(
                        "Live bankroll reconciled after settlement: $%.2f (source=%s)",
                        report.new_bankroll,
                        report.source,
                    )
            except Exception as exc:
                db.rollback()
                logger.warning("Live bankroll reconciliation after settlement failed: %s", exc)

        # Log stats for ALL modes that had settlements
        for m in sorted(modes_with_settlements):
            state = db.query(BotState).filter_by(mode=m).first()
            if not state:
                logger.warning(f"Bot state not found while logging mode {m}")
                continue
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
    """Recalculate bot_state from trade history to prevent drift.

    For live mode, cross-checks against Polymarket API portfolio value
    as the source of truth when on-chain wallet is available.
    """
    try:
        from backend.core.bankroll_reconciliation import reconcile_bot_state as _reconcile

        await _reconcile(db, apply=True, commit=True, source="settlement_reconcile")
        logger.debug("Bot state reconciliation complete")

    except Exception as e:
        logger.error(f"Bot state reconciliation failed: {e}")
        db.rollback()
