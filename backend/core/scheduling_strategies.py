"""Scheduling strategies - background job functions for the trading bot.

This module contains all the async job functions that are scheduled by APScheduler.
Each job is a standalone async function that performs a specific task.
"""
import logging
from datetime import datetime
from sqlalchemy import func

from backend.config import settings
from backend.models.database import SessionLocal, Trade, BotState, Signal, PendingApproval
from backend.core.signals import scan_for_signals
from backend.core.decisions import record_decision
from backend.core.event_bus import _broadcast_event

logger = logging.getLogger("trading_bot")


async def _process_signal_with_approval(
    signal,
    state,
    db,
    trades_executed: int,
    max_trades: int,
) -> int:
    """
    Process a signal through the approval workflow.

    Returns updated trades_executed count.
    """
    from backend.core.scheduler import log_event

    # Check if we already have a trade or pending approval for this market
    existing_trade = db.query(Trade).filter(
        Trade.event_slug == signal.market.slug,
        Trade.settled == False
    ).first()

    existing_pending = db.query(PendingApproval).filter(
        PendingApproval.market_id == signal.market.market_id,
        PendingApproval.status == "pending"
    ).first()

    if existing_trade or existing_pending:
        logger.debug(f"Skipping {signal.market.slug}: already has trade or pending approval")
        return trades_executed

    if trades_executed >= max_trades:
        return trades_executed

    # Get approval mode
    approval_mode = settings.SIGNAL_APPROVAL_MODE
    min_confidence = settings.AUTO_APPROVE_MIN_CONFIDENCE

    # Calculate trade size
    MAX_TRADE_FRACTION = 0.03
    MIN_TRADE_SIZE = 10
    trade_size = min(signal.suggested_size, state.bankroll * MAX_TRADE_FRACTION)
    trade_size = max(trade_size, MIN_TRADE_SIZE)

    if state.bankroll < MIN_TRADE_SIZE:
        log_event("warning", f"Bankroll too low: ${state.bankroll:.2f}")
        return trades_executed

    # Map signal to approval format
    approval_signal = {
        "market_id": signal.market.market_id,
        "market_title": f"BTC {signal.market.window_start.strftime('%H:%M')} - {signal.market.window_end.strftime('%H:%M')} UTC",
        "side": signal.direction.upper(),
        "price": signal.market.up_price if signal.direction == "up" else signal.market.down_price,
        "size": trade_size,
        "confidence": signal.confidence,
        "model_probability": signal.model_probability,
        "market_probability": signal.market_probability,
        "edge": signal.edge,
        "direction": signal.direction,
        "slug": signal.market.slug,
        "up_token_id": signal.market.up_token_id,
        "down_token_id": signal.market.down_token_id,
    }

    # Handle based on approval mode
    if approval_mode == "auto_deny":
        # Auto-deny: skip all signals
        record_decision(
            db, "btc_5m",
            signal.market.market_id,
            "SKIP",
            confidence=signal.confidence,
            signal_data={
                "direction": signal.direction,
                "model_probability": signal.model_probability,
                "market_probability": signal.market_probability,
                "edge": signal.edge,
                "btc_price": getattr(signal, "btc_price", None),
            },
            reason="auto-deny mode: signal rejected"
        )
        log_event("info", f"Auto-denied signal for {signal.market.slug}")
        return trades_executed

    elif approval_mode == "auto_approve" and signal.confidence >= min_confidence:
        # Auto-approve high confidence signals
        return await _execute_trade(signal, state, db, trade_size, trades_executed)

    # Manual approval or low confidence: queue for approval
    return await _queue_for_approval(signal, state, db, trade_size, approval_signal, trades_executed)


async def _execute_trade(signal, state, db, trade_size, trades_executed: int) -> int:
    """Execute a trade immediately."""
    from backend.core.scheduler import log_event
    from backend.data.polymarket_clob import clob_from_settings
    from sqlalchemy.exc import IntegrityError

    # Map up/down to yes/no for storage
    entry_price = signal.market.up_price if signal.direction == "up" else signal.market.down_price

    trade = Trade(
        market_ticker=signal.market.market_id,
        platform="polymarket",
        event_slug=signal.market.slug,
        direction=signal.direction,
        entry_price=entry_price,
        size=trade_size,
        model_probability=signal.model_probability,
        market_price_at_entry=signal.market_probability,
        edge_at_entry=signal.edge,
        trading_mode=settings.TRADING_MODE,
    )

    try:
        db.add(trade)
        db.flush()  # get trade.id
    except IntegrityError:
        # Duplicate trade for this market window - skip
        logger.debug(f"Skipping {signal.market.slug}: trade already exists for this window")
        db.rollback()
        return trades_executed

    # Link trade to the most recent matching Signal and mark it executed
    matching_signal = db.query(Signal).filter(
        Signal.market_ticker == signal.market.market_id,
        Signal.executed == False,
    ).order_by(Signal.timestamp.desc()).first()
    if matching_signal:
        matching_signal.executed = True
        trade.signal_id = matching_signal.id

    trades_executed += 1

    # Execute on-chain for testnet / live modes
    clob_order_id = None
    if settings.TRADING_MODE in ("testnet", "live"):
        token_id = (
            signal.market.up_token_id
            if signal.direction == "up"
            else signal.market.down_token_id
        )
        if token_id:
            try:
                async with clob_from_settings() as clob:
                    result = await clob.place_limit_order(
                        token_id=token_id,
                        side="BUY",
                        price=entry_price,
                        size=trade_size,
                    )
                if result.success:
                    clob_order_id = result.order_id
                    log_event("success",
                        f"[{settings.TRADING_MODE.upper()}] Order placed: {result.order_id}",
                        {"order_id": result.order_id, "mode": settings.TRADING_MODE}
                    )
                else:
                    log_event("warning",
                        f"[{settings.TRADING_MODE.upper()}] Order rejected: {result.error}",
                        {"error": result.error}
                    )
            except Exception as _clob_err:
                log_event("error", f"CLOB execution error: {_clob_err}")
        else:
            log_event("warning",
                f"[{settings.TRADING_MODE.upper()}] No token_id for {signal.market.slug} — order skipped"
            )

    if clob_order_id:
        trade.clob_order_id = clob_order_id

    # Record BUY decision
    try:
        record_decision(
            db, "btc_5m",
            signal.market.market_id,
            "BUY",
            confidence=signal.confidence,
            signal_data={
                "direction": signal.direction,
                "model_probability": signal.model_probability,
                "market_probability": signal.market_probability,
                "edge": signal.edge,
                "btc_price": getattr(signal, "btc_price", None),
                "trade_id": trade.id,
                "trade_size": trade_size,
                "mode": settings.TRADING_MODE,
            },
            reason=f"edge {signal.edge:.3f} >= threshold, {signal.direction} @ {entry_price:.0%}"
        )
    except Exception as _de:
        logger.warning(f"Decision logging (BUY) failed: {_de}")

    # Broadcast event
    try:
        _broadcast_event("trade_opened", {
            "trade_id": trade.id,
            "market_ticker": trade.market_ticker,
            "direction": trade.direction,
            "size": trade.size,
            "entry_price": trade.entry_price,
            "mode": settings.TRADING_MODE,
            "clob_order_id": clob_order_id,
        })
    except Exception:
        pass

    # Send notification
    try:
        from backend.bot.notifier import notify_btc_signal
        notify_btc_signal(signal, trade)
    except Exception:
        pass

    mode_label = f"[{settings.TRADING_MODE.upper()}] " if settings.TRADING_MODE != "paper" else ""
    log_event("trade",
        f"{mode_label}BTC {signal.direction.upper()} ${trade_size:.0f} @ {entry_price:.0%} | {signal.market.slug}",
        {
            "slug": signal.market.slug,
            "direction": signal.direction,
            "size": trade_size,
            "edge": signal.edge,
            "entry_price": entry_price,
            "btc_price": signal.btc_price,
            "clob_order_id": clob_order_id,
        }
    )

    return trades_executed


async def _queue_for_approval(signal, state, db, trade_size, approval_signal, trades_executed: int) -> int:
    """Queue a signal for manual approval."""
    from backend.core.scheduler import log_event

    pending = PendingApproval(
        market_id=signal.market.market_id,
        direction=signal.direction.upper(),
        size=trade_size,
        confidence=signal.confidence,
        signal_data=approval_signal,
        status="pending",
    )
    db.add(pending)
    db.flush()

    # Record decision
    try:
        record_decision(
            db, "btc_5m",
            signal.market.market_id,
            "PENDING",
            confidence=signal.confidence,
            signal_data={
                "direction": signal.direction,
                "model_probability": signal.model_probability,
                "market_probability": signal.market_probability,
                "edge": signal.edge,
                "btc_price": getattr(signal, "btc_price", None),
                "pending_id": pending.id,
                "trade_size": trade_size,
            },
            reason=f"queued for manual approval (conf {signal.confidence:.2f})"
        )
    except Exception as _de:
        logger.warning(f"Decision logging (PENDING) failed: {_de}")

    # Broadcast event
    try:
        _broadcast_event("signal_found", {
            "market_ticker": signal.market.market_id,
            "market_title": f"BTC {signal.market.window_start.strftime('%H:%M')} - {signal.market.window_end.strftime('%H:%M')} UTC",
            "direction": signal.direction,
            "model_probability": signal.model_probability,
            "market_probability": signal.market_probability,
            "edge": signal.edge,
            "confidence": signal.confidence,
            "suggested_size": trade_size,
            "reasoning": "Signal queued for approval",
            "timestamp": datetime.utcnow().isoformat(),
            "category": "trading",
            "btc_price": getattr(signal, "btc_price", None),
            "window_end": signal.market.window_end.isoformat() if signal.market.window_end else None,
            "actionable": True,
            "event_slug": signal.market.slug,
        })
    except Exception:
        pass

    log_event("info", f"Queued signal for approval: {signal.market.slug} (conf {signal.confidence:.2f})")

    return trades_executed


async def scan_and_trade_job():
    """
    Background job: Scan BTC 5-min markets, generate signals, execute trades.
    Runs every minute.
    """
    from backend.core.scheduler import log_event

    log_event("info", "Scanning BTC 5-min markets...")

    try:
        signals = await scan_for_signals()
        actionable = [s for s in signals if s.passes_threshold]

        # AI enhancement: if enabled, enrich actionable signals with AI analysis
        if settings.AI_ENABLED and actionable:
            try:
                from backend.ai.market_analyzer import analyze_market
                from backend.ai.ensemble import EnsembleSignalGenerator

                ensemble = EnsembleSignalGenerator(weights={
                    "technical": max(0.10, 1.0 - settings.AI_SIGNAL_WEIGHT),
                    "ai": settings.AI_SIGNAL_WEIGHT,
                    "orderbook": 0.0,
                    "data_quality": 0.0,
                })

                for sig in actionable:
                    try:
                        question = getattr(sig.market, 'slug', '') or 'BTC 5-min Up/Down'
                        ai_result = await analyze_market(
                            question=question,
                            current_price=sig.market_probability,
                            volume=getattr(sig.market, 'volume', 0),
                            category="crypto",
                        )
                        if ai_result:
                            combined = ensemble.combine_signals(
                                technical_prob=sig.model_probability,
                                ai_prob=ai_result.probability,
                                market_price=sig.market_probability,
                            )
                            sig.model_probability = combined.combined_probability
                            sig.edge = combined.edge
                            sig.confidence = min(sig.confidence, ai_result.confidence)
                            log_event("data", f"AI enhanced signal: edge={combined.edge:.3f} (was {sig.edge:.3f})")
                    except Exception as ai_err:
                        logger.debug("AI enhancement failed for signal, using technical only: %s", ai_err)
            except ImportError:
                logger.debug("AI modules not available, using technical signals only")

        log_event("data", f"Found {len(signals)} signals, {len(actionable)} actionable", {
            "total_signals": len(signals),
            "actionable": len(actionable),
            "ai_enabled": settings.AI_ENABLED,
        })

        # Record SKIP decisions for all non-actionable signals (before the early return)
        if signals:
            db_skip = SessionLocal()
            try:
                from backend.core.decisions import record_decision
                for sig in signals:
                    if not sig.passes_threshold:
                        record_decision(
                            db_skip, "btc_5m",
                            getattr(sig.market, "market_id", "unknown"),
                            "SKIP",
                            confidence=sig.confidence,
                            signal_data={
                                "direction": sig.direction,
                                "model_probability": sig.model_probability,
                                "market_probability": sig.market_probability,
                                "edge": sig.edge,
                                "btc_price": getattr(sig, "btc_price", None),
                            },
                            reason=f"edge {sig.edge:.3f} below threshold"
                        )
                db_skip.commit()
            except Exception as _de:
                logger.warning(f"Decision logging (SKIP) failed: {_de}")
                db_skip.rollback()
            finally:
                db_skip.close()

        if not actionable:
            log_event("info", "No actionable BTC signals")
            return

        db = SessionLocal()
        try:
            state = db.query(BotState).first()
            if not state:
                log_event("error", "Bot state not initialized")
                return

            if not state.is_running:
                log_event("info", "Bot is paused, skipping trades")
                return

            MAX_TRADES_PER_SCAN = 2
            MIN_TRADE_SIZE = 10
            MAX_TRADE_FRACTION = 0.03  # 3% max per trade
            MAX_TOTAL_PENDING = settings.MAX_TOTAL_PENDING_TRADES

            # --- Daily loss circuit breaker ---
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_pnl = db.query(func.coalesce(func.sum(Trade.pnl), 0.0)).filter(
                Trade.settled == True,
                Trade.settlement_time >= today_start
            ).scalar()

            if daily_pnl <= -settings.DAILY_LOSS_LIMIT:
                log_event("warning", f"Daily loss limit hit: ${daily_pnl:.2f} (limit: -${settings.DAILY_LOSS_LIMIT:.0f}). Stopping trades.")
                return

            total_pending = db.query(Trade).filter(Trade.settled == False).count()
            if total_pending >= MAX_TOTAL_PENDING:
                log_event("info", f"Max pending trades reached ({total_pending}/{MAX_TOTAL_PENDING})")
                return

            # Process signals through approval workflow
            MAX_TRADES_PER_SCAN = 2
            trades_executed = 0

            for signal in actionable[:MAX_TRADES_PER_SCAN]:
                trades_executed = await _process_signal_with_approval(
                    signal, state, db, trades_executed, MAX_TRADES_PER_SCAN
                )

            state.last_run = datetime.utcnow()
            db.commit()

            if trades_executed > 0:
                log_event("success", f"Executed {trades_executed} BTC trade(s)")
            else:
                log_event("info", "No new trades executed")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Scan error: {str(e)}")
        logger.exception("Error in scan_and_trade_job")


async def weather_scan_and_trade_job():
    """
    Background job: Scan weather temperature markets, generate signals, execute trades.
    Runs every 5 minutes when WEATHER_ENABLED.
    """
    from backend.core.scheduler import log_event

    log_event("info", "Scanning weather temperature markets...")

    try:
        from backend.core.weather_signals import scan_for_weather_signals

        signals = await scan_for_weather_signals()
        actionable = [s for s in signals if s.passes_threshold]

        log_event("data", f"Weather: {len(signals)} signals, {len(actionable)} actionable", {
            "total_signals": len(signals),
            "actionable": len(actionable),
        })

        if not actionable:
            log_event("info", "No actionable weather signals")
            return

        db = SessionLocal()
        try:
            state = db.query(BotState).first()
            if not state:
                log_event("error", "Bot state not initialized")
                return

            if not state.is_running:
                log_event("info", "Bot is paused, skipping weather trades")
                return

            MAX_TRADES_PER_SCAN = 3
            MIN_TRADE_SIZE = 10
            MAX_WEATHER_ALLOCATION = 500.0  # Max total exposure to weather markets

            # Check weather allocation limit
            weather_pending = db.query(func.coalesce(func.sum(Trade.size), 0.0)).filter(
                Trade.settled == False,
                Trade.market_type == "weather",
            ).scalar()

            if weather_pending >= MAX_WEATHER_ALLOCATION:
                log_event("info", f"Weather allocation limit reached: ${weather_pending:.0f}/${MAX_WEATHER_ALLOCATION:.0f}")
                return

            trades_executed = 0
            for signal in actionable[:MAX_TRADES_PER_SCAN]:
                # Check if we already have a trade for this market
                existing = db.query(Trade).filter(
                    Trade.market_ticker == signal.market.market_id,
                    Trade.settled == False,
                ).first()

                if existing:
                    continue

                trade_size = min(signal.suggested_size, settings.WEATHER_MAX_TRADE_SIZE)
                trade_size = max(trade_size, MIN_TRADE_SIZE)

                if state.bankroll < MIN_TRADE_SIZE:
                    log_event("warning", f"Bankroll too low: ${state.bankroll:.2f}")
                    break

                if trades_executed >= MAX_TRADES_PER_SCAN:
                    break

                entry_price = signal.market.yes_price if signal.direction == "yes" else signal.market.no_price

                trade = Trade(
                    market_ticker=signal.market.market_id,
                    platform="polymarket",
                    event_slug=signal.market.slug,
                    market_type="weather",
                    direction=signal.direction,
                    entry_price=entry_price,
                    size=trade_size,
                    model_probability=signal.model_probability,
                    market_price_at_entry=signal.market_probability,
                    edge_at_entry=signal.edge,
                    trading_mode=settings.TRADING_MODE,
                )

                db.add(trade)
                db.flush()

                # Link to signal record
                matching_signal = db.query(Signal).filter(
                    Signal.market_ticker == signal.market.market_id,
                    Signal.market_type == "weather",
                    Signal.executed == False,
                ).order_by(Signal.timestamp.desc()).first()
                if matching_signal:
                    matching_signal.executed = True
                    trade.signal_id = matching_signal.id

                trades_executed += 1

                try:
                    from backend.core.event_bus import _broadcast_event
                    _broadcast_event("trade_opened", {
                        "trade_id": trade.id,
                        "market_ticker": trade.market_ticker,
                        "direction": trade.direction,
                        "size": trade.size,
                        "entry_price": trade.entry_price,
                        "mode": settings.TRADING_MODE,
                    })
                except Exception:
                    pass

                log_event("trade",
                    f"WX {signal.market.city_name}: {signal.direction.upper()} "
                    f"${trade_size:.0f} @ {entry_price:.0%} | "
                    f"{signal.market.metric} {signal.market.direction} {signal.market.threshold_f:.0f}F",
                    {
                        "slug": signal.market.slug,
                        "direction": signal.direction,
                        "size": trade_size,
                        "edge": signal.edge,
                        "entry_price": entry_price,
                        "city": signal.market.city_name,
                    }
                )

            state.last_run = datetime.utcnow()
            db.commit()

            if trades_executed > 0:
                log_event("success", f"Executed {trades_executed} weather trade(s)")
            else:
                log_event("info", "No new weather trades executed")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Weather scan error: {str(e)}")
        logger.exception("Error in weather_scan_and_trade_job")


async def settlement_job():
    """
    Background job: Check and settle pending trades.
    Runs every 2 minutes (BTC 5-min markets resolve fast).
    """
    from backend.core.scheduler import log_event

    log_event("info", "Checking BTC trade settlements...")

    try:
        from backend.core.settlement import settle_pending_trades, update_bot_state_with_settlements

        db = SessionLocal()
        try:
            pending_count = db.query(Trade).filter(Trade.settled == False).count()

            if pending_count == 0:
                log_event("data", "No pending trades to settle")
                return

            log_event("data", f"Processing {pending_count} pending trades")

            settled = await settle_pending_trades(db)

            if settled:
                await update_bot_state_with_settlements(db, settled)

                wins = sum(1 for t in settled if t.result == "win")
                losses = sum(1 for t in settled if t.result == "loss")
                total_pnl = sum(t.pnl for t in settled if t.pnl is not None)

                log_event("success", f"Settled {len(settled)} trades: {wins}W/{losses}L, P&L: ${total_pnl:.2f}", {
                    "settled_count": len(settled),
                    "wins": wins,
                    "losses": losses,
                    "pnl": total_pnl
                })

                from backend.bot.notifier import notify_trade_settled
                for trade in settled:
                    result_prefix = "+" if trade.pnl and trade.pnl > 0 else ""
                    log_event("data", f"  {trade.event_slug}: {trade.result.upper()} {result_prefix}${trade.pnl:.2f}")
                    notify_trade_settled(trade)
            else:
                log_event("info", "No trades ready for settlement")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Settlement error: {str(e)}")
        logger.exception("Error in settlement_job")


async def news_feed_scan_job():
    """Periodically pull news feeds when NEWS_FEED_ENABLED."""
    from backend.core.scheduler import log_event

    if not settings.NEWS_FEED_ENABLED:
        return
    try:
        from backend.data.feed_aggregator import FeedAggregator
        agg = FeedAggregator()
        items = await agg.fetch_all()
        log_event("data", f"News feed: {len(items)} items")
    except Exception as e:
        log_event("error", f"news_feed_scan error: {e}")


async def arbitrage_scan_job():
    """Periodically scan for arbitrage opportunities when ARBITRAGE_DETECTOR_ENABLED."""
    from backend.core.scheduler import log_event

    if not settings.ARBITRAGE_DETECTOR_ENABLED:
        return
    try:
        from backend.core.arbitrage_detector import ArbitrageDetector
        from backend.core.market_scanner import fetch_all_active_markets
        markets = await fetch_all_active_markets(limit=300)
        det = ArbitrageDetector()
        market_dicts = [
            {
                "market_id": m.ticker or m.slug,
                "yes_price": m.yes_price,
                "no_price": m.no_price,
                "question": m.question,
            }
            for m in markets
        ]
        ops = det.scan_all(market_dicts)
        log_event("data", f"Arbitrage scan: {len(ops)} opportunities from {len(market_dicts)} markets")
    except Exception as e:
        log_event("error", f"arbitrage_scan error: {e}")


async def auto_trader_job():
    """Run AutoTrader against unexecuted signals when AUTO_TRADER_ENABLED."""
    from backend.core.scheduler import log_event

    if not settings.AUTO_TRADER_ENABLED:
        return
    try:
        from backend.core.auto_trader import AutoTrader
        from backend.core.risk_manager import RiskManager

        trader = AutoTrader(RiskManager())
        db = SessionLocal()
        try:
            state = db.query(BotState).first()
            if not state or not state.is_running:
                return

            signals = (
                db.query(Signal)
                .filter(Signal.executed == False)
                .order_by(Signal.timestamp.desc())
                .limit(10)
                .all()
            )
            if not signals:
                return

            current_exposure = float(
                db.query(func.coalesce(func.sum(Trade.size), 0.0))
                .filter(Trade.settled == False)
                .scalar()
                or 0.0
            )

            executed = 0
            queued = 0
            for sig in signals:
                signal_dict = {
                    "market_id": sig.market_ticker,
                    "side": "BUY",
                    "confidence": getattr(sig, "confidence", 0.0) or 0.0,
                    "size": min(50.0, state.bankroll * 0.03),
                    "price": getattr(sig, "model_probability", 0.5) or 0.5,
                    "token_id": None,
                }
                result = await trader.execute_signal(
                    signal_dict,
                    bankroll=state.bankroll,
                    current_exposure=current_exposure,
                )
                if result.executed:
                    executed += 1
                elif result.pending_approval:
                    queued += 1
            log_event("data", f"AutoTrader cycle: executed={executed} queued={queued}")
        finally:
            db.close()
    except Exception as e:
        log_event("error", f"auto_trader_job error: {e}")


async def heartbeat_job():
    """Periodic heartbeat. Runs every minute."""
    from backend.core.scheduler import log_event

    db = None
    try:
        db = SessionLocal()
        state = db.query(BotState).first()
        pending = db.query(Trade).filter(Trade.settled == False).count()

        if state is None:
            log_event("warning", "Heartbeat: Bot state not initialized")
            return

        log_event("data", f"Heartbeat: {pending} pending trades, bankroll: ${state.bankroll:.2f}", {
            "pending_trades": pending,
            "bankroll": state.bankroll,
            "is_running": state.is_running
        })
    except Exception as e:
        log_event("warning", f"Heartbeat failed: {str(e)}")
    finally:
        if db:
            db.close()


async def strategy_cycle_job(strategy_name: str) -> None:
    """Generic strategy dispatcher — called by APScheduler for each enabled strategy."""
    from backend.core.scheduler import log_event

    from backend.strategies.registry import STRATEGY_REGISTRY
    from backend.models.database import SessionLocal, StrategyConfig
    import json

    db = SessionLocal()
    try:
        config = db.query(StrategyConfig).filter(
            StrategyConfig.strategy_name == strategy_name,
            StrategyConfig.enabled == True,
        ).first()

        if not config:
            log_event("info", f"Strategy {strategy_name} disabled or not configured, skipping")
            return

        strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
        if not strategy_cls:
            log_event("warning", f"Strategy {strategy_name} not in registry")
            return

        params = {}
        if config.params:
            try:
                params = json.loads(config.params)
            except Exception:
                pass

        from backend.strategies.base import StrategyContext
        from backend.config import settings as _settings

        ctx = StrategyContext(
            db=db,
            clob=None,  # strategies use their own CLOB if needed
            settings=_settings,
            logger=logger,
            params=params,
            mode=_settings.TRADING_MODE,
        )

        strategy = strategy_cls()
        result = await strategy.run(ctx)

        # Execute BUY decisions via the strategy executor pipeline
        from backend.core.strategy_executor import execute_decisions as _exec_decisions

        buy_decisions = [
            d for d in getattr(result, "decisions", [])
            if isinstance(d, dict) and d.get("decision") == "BUY" and d.get("market_ticker")
        ]
        if buy_decisions:
            trade_results = await _exec_decisions(buy_decisions, strategy_name)
            logger.info(f"Strategy {strategy_name}: executed {len(trade_results)} trades")

        log_event("info", f"Strategy {strategy_name} cycle done: decisions={result.decisions_recorded} trades={result.trades_placed} errors={len(result.errors)}")

    except Exception as e:
        log_event("error", f"Strategy cycle job failed for {strategy_name}: {e}")
        logger.exception(f"strategy_cycle_job({strategy_name})")
    finally:
        db.close()
