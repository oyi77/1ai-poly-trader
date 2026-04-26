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
    fetch_polymarket_resolution,
    fetch_resolution_for_trade,
    calculate_pnl,
    _resolve_markets,
    _parse_market_resolution,
    check_market_settlement,
    process_settled_trade,
)

logger = logging.getLogger("trading_bot")

_settlement_lock = asyncio.Lock()


async def _fetch_pm_portfolio_value() -> float | None:
    """Fetch on-chain portfolio value from Polymarket Data API."""
    try:
        import httpx
        wallet = settings.POLYMARKET_BUILDER_ADDRESS
        if not wallet:
            return None
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://data-api.polymarket.com/value",
                params={"user": wallet.lower()},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return float(data[0].get("value", 0))
                elif isinstance(data, dict):
                    return float(data.get("value", 0))
    except Exception as e:
        logger.debug(f"PM portfolio value fetch failed: {e}")
    return None


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
                            trade.result = "closed"
                            trade.settlement_time = now
                            trade.pnl = 0.0
                            trade.settlement_value = None
                            logger.info(
                                f"Position reconciliation: trade {trade.id} closed without resolution (position gone)"
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
            state = db.query(BotState).filter_by(mode=trading_mode).first()
            if not state:
                logger.warning(f"Bot state not found for mode {trading_mode}")
                continue

            is_real_trade = trade.result in ("win", "loss")
            is_expired_or_push = trade.result in ("expired", "push", "closed")

            # Route updates to mode-specific fields
            if trading_mode == "paper":
                if is_real_trade:
                    state.paper_pnl = (state.paper_pnl or 0.0) + trade.pnl
                    state.paper_bankroll = (state.paper_bankroll or 0.0) + trade.size + trade.pnl
                    state.paper_trades = (state.paper_trades or 0) + 1
                    if trade.result == "win":
                        state.paper_wins = (state.paper_wins or 0) + 1
                elif is_expired_or_push:
                    state.paper_bankroll = (state.paper_bankroll or 0.0) + trade.size
                    logger.info(
                        f"Expired/push trade {trade.id}: returned ${trade.size:.2f} to paper bankroll"
                    )
            elif trading_mode == "testnet":
                if is_real_trade:
                    state.testnet_pnl = (state.testnet_pnl or 0.0) + trade.pnl
                    state.testnet_bankroll = (state.testnet_bankroll or 0.0) + trade.size + trade.pnl
                    state.testnet_trades = (state.testnet_trades or 0) + 1
                    if trade.result == "win":
                        state.testnet_wins = (state.testnet_wins or 0) + 1
                elif is_expired_or_push:
                    state.testnet_bankroll = (state.testnet_bankroll or 0.0) + trade.size
                    logger.info(
                        f"Expired/push trade {trade.id}: returned ${trade.size:.2f} to testnet bankroll"
                    )
            else:  # live mode
                if is_real_trade:
                    state.total_pnl = (state.total_pnl or 0.0) + trade.pnl
                    state.total_trades = (state.total_trades or 0) + 1
                    if trade.result == "win":
                        state.winning_trades = (state.winning_trades or 0) + 1

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

        # Sync live bankroll from PM API (source of truth)
        if "live" in {
            getattr(t, "trading_mode", "paper") or "paper"
            for t in settled_trades
            if t.pnl is not None
        }:
            pm_val = await _fetch_pm_portfolio_value()
            if pm_val is not None and pm_val > 0:
                live_state = db.query(BotState).filter_by(mode="live").first()
                if live_state:
                    live_state.bankroll = round(pm_val, 2)
                    live_state.total_pnl = round(pm_val - float(settings.INITIAL_BANKROLL), 2)
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                    logger.info(f"Live bankroll synced from PM API: ${pm_val:.2f}")

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
    """Recalculate bot_state from trade history to prevent drift.

    For live mode, cross-checks against Polymarket API portfolio value
    as the source of truth when on-chain wallet is available.
    """
    try:
        from sqlalchemy import func, case

        for mode in ("paper", "testnet", "live"):
            state = db.query(BotState).filter_by(mode=mode).first()
            if not state:
                continue

            if mode == "live":
                pm_value = await _fetch_pm_portfolio_value()
                if pm_value is not None and pm_value > 0:
                    drift = abs(float(state.bankroll or 0) - pm_value)
                    if drift > 1.0:
                        logger.warning(
                            f"Live bankroll drift vs PM API: "
                            f"DB=${float(state.bankroll or 0):.2f} PM=${pm_value:.2f}"
                        )
                        state.bankroll = round(pm_value, 2)
                        from backend.config import settings as _s
                        state.total_pnl = round(pm_value - float(_s.INITIAL_BANKROLL), 2)
                        logger.info(f"Live bankroll reconciled from PM API: ${pm_value:.2f}")
                    continue

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

            initial_bankroll = settings.INITIAL_BANKROLL if mode != "testnet" else 100.0
            drift_bankroll = abs(
                (state.bankroll or 0)
                - (initial_bankroll + realized_pnl - open_exposure)
            )
            drift_pnl = abs((state.total_pnl or 0) - realized_pnl)
            
            if drift_bankroll > 0.01 or drift_pnl > 0.01:
                logger.warning(
                    f"Bot state drift detected ({mode})! "
                    f"Bankroll Δ${drift_bankroll:.2f}, PNL Δ${drift_pnl:.2f}"
                )
                state.bankroll = round(initial_bankroll + realized_pnl - open_exposure, 2)
                state.total_pnl = realized_pnl
                state.total_trades = trade_count
                state.winning_trades = win_count
                logger.info(f"Bot state reconciled from trade history ({mode})")

        db.commit()
        logger.debug("Bot state reconciliation complete")

    except Exception as e:
        logger.error(f"Bot state reconciliation failed: {e}")
        db.rollback()
