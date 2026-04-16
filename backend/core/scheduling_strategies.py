"""Background job functions scheduled by APScheduler."""

import logging
from datetime import datetime, timezone
from sqlalchemy import func

from backend.config import settings
from backend.models.database import (
    SessionLocal,
    Trade,
    BotState,
    Signal,
    PendingApproval,
    StrategyConfig,
)
from backend.core.signals import scan_for_signals
from backend.core.decisions import record_decision
from backend.core.event_bus import _broadcast_event

logger = logging.getLogger("trading_bot")


def _get_effective_mode(db, strategy_name: str) -> str:
    """Resolve per-strategy trading mode, falling back to global settings.TRADING_MODE."""
    config = (
        db.query(StrategyConfig)
        .filter(StrategyConfig.strategy_name == strategy_name)
        .first()
    )
    if config and config.trading_mode:
        return config.trading_mode
    return settings.TRADING_MODE


def _get_bankroll_for_mode(state, mode: str) -> float:
    """Read the correct bankroll field based on trading mode."""
    if mode == "paper":
        return (
            state.paper_bankroll
            if state.paper_bankroll is not None
            else settings.INITIAL_BANKROLL
        )
    elif mode == "testnet":
        return (
            state.testnet_bankroll
            if state.testnet_bankroll is not None
            else settings.INITIAL_BANKROLL
        )
    else:
        return (
            state.bankroll if state.bankroll is not None else settings.INITIAL_BANKROLL
        )


async def _process_signal_with_approval(
    signal,
    state,
    db,
    trades_executed: int,
    max_trades: int,
    effective_mode: str = None,
) -> int:
    from backend.core.scheduler import log_event

    mode = effective_mode or settings.TRADING_MODE

    existing_trade = (
        db.query(Trade)
        .filter(
            Trade.event_slug == signal.market.slug,
            Trade.settled.is_(False),
            Trade.trading_mode == mode,
        )
        .first()
    )
    if existing_trade:
        logger.debug(f"Skipping {signal.market.slug}: already has open trade")
        return trades_executed

    if trades_executed >= max_trades:
        return trades_executed

    approval_mode = settings.SIGNAL_APPROVAL_MODE

    existing_pending = (
        db.query(PendingApproval)
        .filter(
            PendingApproval.market_id == signal.market.market_id,
            PendingApproval.status == "pending",
        )
        .first()
    )

    if existing_pending:
        if approval_mode == "manual":
            logger.debug(f"Skipping {signal.market.slug}: already has pending approval")
            return trades_executed
        else:
            existing_pending.status = "expired"
            db.flush()
            logger.debug(
                f"Auto-expired stale pending approval for {signal.market.slug} (mode={approval_mode})"
            )
    min_confidence = settings.AUTO_APPROVE_MIN_CONFIDENCE

    MAX_TRADE_FRACTION = 0.03
    MIN_TRADE_SIZE = 10
    bankroll = _get_bankroll_for_mode(state, mode)
    trade_size = min(signal.suggested_size, bankroll * MAX_TRADE_FRACTION)
    trade_size = max(trade_size, MIN_TRADE_SIZE)

    if bankroll < MIN_TRADE_SIZE:
        log_event("warning", f"Bankroll too low: ${bankroll:.2f}")
        return trades_executed

    approval_signal = {
        "market_id": signal.market.market_id,
        "market_title": f"BTC {signal.market.window_start.strftime('%H:%M')} - {signal.market.window_end.strftime('%H:%M')} UTC",
        "side": signal.direction.upper(),
        "price": signal.market.up_price
        if signal.direction == "up"
        else signal.market.down_price,
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

    if approval_mode == "auto_deny":
        record_decision(
            db,
            "btc_5m",
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
            reason="auto-deny mode: signal rejected",
        )
        log_event("info", f"Auto-denied signal for {signal.market.slug}")
        return trades_executed

    elif approval_mode == "auto_approve":
        if signal.confidence >= min_confidence:
            return await _execute_trade(
                signal, state, db, trade_size, trades_executed, mode=mode
            )
        else:
            log_event(
                "info",
                f"Auto-approve: skipping low-confidence signal ({signal.confidence:.2f} < {min_confidence}) for {signal.market.slug}",
            )
            return trades_executed

    return await _queue_for_approval(
        signal, state, db, trade_size, approval_signal, trades_executed
    )


async def _execute_trade(
    signal, state, db, trade_size, trades_executed: int, mode: str = None
) -> int:
    """Execute a BTC trade by delegating to strategy_executor.execute_decision()."""
    from backend.core.scheduler import log_event
    from backend.core.strategy_executor import execute_decision

    entry_price = (
        signal.market.up_price if signal.direction == "up" else signal.market.down_price
    )
    token_id = (
        signal.market.up_token_id
        if signal.direction == "up"
        else signal.market.down_token_id
    )

    decision = {
        "market_ticker": signal.market.market_id,
        "slug": signal.market.slug,
        "event_slug": signal.market.slug,
        "direction": signal.direction,
        "size": trade_size,
        "entry_price": entry_price,
        "edge": signal.edge,
        "confidence": signal.confidence,
        "model_probability": signal.model_probability,
        "token_id": token_id,
        "platform": "polymarket",
        "reasoning": f"edge {signal.edge:.3f} >= threshold, {signal.direction} @ {entry_price:.0%}",
    }

    result = await execute_decision(decision, "btc_5m", db=db)
    if result is None:
        return trades_executed

    trades_executed += 1

    try:
        from backend.bot.notifier import notify_btc_signal

        notify_btc_signal(signal, None)
    except Exception:
        pass

    mode_label = f"[{mode.upper()}] " if mode != "paper" else ""
    log_event(
        "trade",
        f"{mode_label}BTC {signal.direction.upper()} ${trade_size:.0f} @ {entry_price:.0%} | {signal.market.slug}",
        {
            "slug": signal.market.slug,
            "direction": signal.direction,
            "size": trade_size,
            "edge": signal.edge,
            "entry_price": entry_price,
            "btc_price": getattr(signal, "btc_price", None),
        },
    )

    return trades_executed


async def _queue_for_approval(
    signal, state, db, trade_size, approval_signal, trades_executed: int
) -> int:
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

    try:
        record_decision(
            db,
            "btc_5m",
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
            reason=f"queued for manual approval (conf {signal.confidence:.2f})",
        )
    except Exception as _de:
        logger.warning(f"Decision logging (PENDING) failed: {_de}")

    try:
        _broadcast_event(
            "signal_found",
            {
                "market_ticker": signal.market.market_id,
                "market_title": f"BTC {signal.market.window_start.strftime('%H:%M')} - {signal.market.window_end.strftime('%H:%M')} UTC",
                "direction": signal.direction,
                "model_probability": signal.model_probability,
                "market_probability": signal.market_probability,
                "edge": signal.edge,
                "confidence": signal.confidence,
                "suggested_size": trade_size,
                "reasoning": "Signal queued for approval",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": "trading",
                "btc_price": getattr(signal, "btc_price", None),
                "window_end": signal.market.window_end.isoformat()
                if signal.market.window_end
                else None,
                "actionable": True,
                "event_slug": signal.market.slug,
            },
        )
    except Exception:
        pass

    log_event(
        "info",
        f"Queued signal for approval: {signal.market.slug} (conf {signal.confidence:.2f})",
    )

    return trades_executed


async def scan_and_trade_job():
    """Run BTC Oracle strategy. Runs every minute."""
    from backend.core.scheduler import log_event
    from backend.strategies.btc_oracle import BtcOracleStrategy
    from backend.strategies.base import StrategyContext

    log_event("info", "Running BTC Oracle strategy (replaces broken momentum)...")

    db = SessionLocal()
    try:
        state = db.query(BotState).first()
        if not state:
            log_event("error", "Bot state not initialized")
            return

        if not state.is_running:
            log_event("info", "Bot is paused, skipping trades")
            return

        btc_mode = _get_effective_mode(db, "btc_oracle")

        ctx = StrategyContext(
            db=db,
            clob=None,
            settings=settings,
            logger=logger,
            params={},
            mode=btc_mode,
        )

        strategy = BtcOracleStrategy()
        result = await strategy.run(ctx)

        buy_decisions = [
            d
            for d in getattr(result, "decisions", [])
            if isinstance(d, dict)
            and d.get("decision") == "BUY"
            and d.get("market_ticker")
        ]

        if buy_decisions:
            try:
                from backend.core.strategy_executor import execute_decisions

                executed = await execute_decisions(buy_decisions, "btc_oracle", db=db)
                log_event("success", f"BTC Oracle: executed {len(executed)} trade(s)")
            except Exception as exec_err:
                log_event("error", f"BTC Oracle execution failed: {exec_err}")
        else:
            log_event("info", "BTC Oracle: no actionable signals")

        state.last_run = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        log_event("error", f"BTC Oracle error: {str(e)}")
        logger.exception("Error in scan_and_trade_job (btc_oracle)")
    finally:
        db.close()


async def weather_scan_and_trade_job():
    """Scan weather temperature markets and execute trades. Runs every 5 minutes."""
    from backend.core.scheduler import log_event
    from backend.core.heartbeat import update_heartbeat as _update_hb

    log_event("info", "Scanning weather temperature markets...")

    try:
        from backend.core.weather_signals import scan_for_weather_signals

        weather_mode = _get_effective_mode(SessionLocal(), "weather")

        signals = await scan_for_weather_signals(mode=weather_mode)
        actionable = [s for s in signals if s.passes_threshold]

        log_event(
            "data",
            f"Weather: {len(signals)} signals, {len(actionable)} actionable",
            {
                "total_signals": len(signals),
                "actionable": len(actionable),
            },
        )

        if not actionable:
            log_event("info", "No actionable weather signals")
            # Still update heartbeat so watchdog knows we ran
            hb_db = SessionLocal()
            try:
                _update_hb(hb_db, "weather_emos")
            finally:
                hb_db.close()
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
            MAX_WEATHER_ALLOCATION = 500.0
            weather_mode = _get_effective_mode(db, "weather")

            weather_pending = (
                db.query(func.coalesce(func.sum(Trade.size), 0.0))
                .filter(
                    Trade.settled.is_(False),
                    Trade.market_type == "weather",
                    Trade.trading_mode == weather_mode,
                )
                .scalar()
            )

            if weather_pending >= MAX_WEATHER_ALLOCATION:
                log_event(
                    "info",
                    f"Weather allocation limit reached: ${weather_pending:.0f}/${MAX_WEATHER_ALLOCATION:.0f}",
                )
                return

            trades_executed = 0
            for signal in actionable[:MAX_TRADES_PER_SCAN]:
                existing = (
                    db.query(Trade)
                    .filter(
                        Trade.market_ticker == signal.market.market_id,
                        Trade.settled.is_(False),
                        Trade.trading_mode == weather_mode,
                    )
                    .first()
                )

                if existing:
                    continue

                trade_size = min(signal.suggested_size, settings.WEATHER_MAX_TRADE_SIZE)
                trade_size = max(trade_size, MIN_TRADE_SIZE)

                bankroll = _get_bankroll_for_mode(state, weather_mode)
                if bankroll < MIN_TRADE_SIZE:
                    log_event("warning", f"Bankroll too low: ${bankroll:.2f}")
                    break

                if trades_executed >= MAX_TRADES_PER_SCAN:
                    break

                from backend.core.strategy_executor import execute_decision

                entry_price = (
                    signal.market.yes_price
                    if signal.direction == "yes"
                    else signal.market.no_price
                )
                token_id = (
                    getattr(signal.market, "token_id", None) or signal.market.market_id
                )

                decision = {
                    "market_ticker": signal.market.market_id,
                    "event_slug": signal.market.slug,
                    "direction": signal.direction,
                    "size": trade_size,
                    "entry_price": entry_price,
                    "edge": signal.edge,
                    "confidence": signal.model_probability,
                    "model_probability": signal.model_probability,
                    "token_id": token_id,
                    "platform": "polymarket",
                    "market_type": "weather",
                    "reasoning": f"weather signal: {signal.market.city_name}",
                }
                result = await execute_decision(decision, "weather", db=db)
                if result is None:
                    continue

                trades_executed += 1
                log_event(
                    "trade",
                    f"WX {signal.market.city_name}: {signal.direction.upper()} "
                    f"${trade_size:.0f} @ {entry_price:.0%}",
                    {
                        "slug": signal.market.slug,
                        "direction": signal.direction,
                        "size": trade_size,
                        "edge": signal.edge,
                        "city": signal.market.city_name,
                    },
                )

            state.last_run = datetime.now(timezone.utc)
            db.commit()

            if trades_executed > 0:
                log_event("success", f"Executed {trades_executed} weather trade(s)")
            else:
                log_event("info", "No new weather trades executed")

            _update_hb(db, "weather_emos")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Weather scan error: {str(e)}")
        logger.exception("Error in weather_scan_and_trade_job")


async def settlement_job():
    """Check and settle pending trades. Runs every 2 minutes."""
    from backend.core.scheduler import log_event

    log_event("info", "Checking BTC trade settlements...")

    try:
        from backend.core.settlement import (
            settle_pending_trades,
            update_bot_state_with_settlements,
            reconcile_bot_state,
        )

        db = SessionLocal()
        try:
            pending_count = (
                db.query(Trade)
                .filter(
                    Trade.settled.is_(False),
                )
                .count()
            )

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

                log_event(
                    "success",
                    f"Settled {len(settled)} trades: {wins}W/{losses}L, P&L: ${total_pnl:.2f}",
                    {
                        "settled_count": len(settled),
                        "wins": wins,
                        "losses": losses,
                        "pnl": total_pnl,
                    },
                )

                from backend.bot.notifier import notify_trade_settled

                for trade in settled:
                    result_prefix = "+" if trade.pnl and trade.pnl > 0 else ""
                    log_event(
                        "data",
                        f"  {trade.event_slug}: {trade.result.upper()} {result_prefix}${trade.pnl:.2f}",
                    )
                    notify_trade_settled(trade)
            else:
                log_event("info", "No trades ready for settlement")

            await reconcile_bot_state(db)

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
        log_event(
            "data",
            f"Arbitrage scan: {len(ops)} opportunities from {len(market_dicts)} markets",
        )
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
        from backend.data.polymarket_clob import clob_from_settings

        trader = AutoTrader(RiskManager(), clob_factory=clob_from_settings)
        db = SessionLocal()
        try:
            state = db.query(BotState).first()
            if not state or not state.is_running:
                return

            auto_trader_mode = _get_effective_mode(db, "auto_trader")
            bankroll = _get_bankroll_for_mode(state, auto_trader_mode)

            signals = (
                db.query(Signal)
                .filter(
                    Signal.executed.is_(False),
                    Signal.execution_mode == auto_trader_mode,
                )
                .order_by(Signal.timestamp.desc())
                .limit(10)
                .all()
            )
            if not signals:
                log_event("info", "AutoTrader cycle: no pending signals")
                return

            current_exposure = float(
                db.query(func.coalesce(func.sum(Trade.size), 0.0))
                .filter(
                    Trade.settled.is_(False),
                    Trade.trading_mode == auto_trader_mode,
                )
                .scalar()
                or 0.0
            )

            executed = 0
            queued = 0
            skipped = 0
            for sig in signals:
                token_id = getattr(sig, "token_id", None)
                if auto_trader_mode in ("testnet", "live") and not token_id:
                    sig.executed = True
                    skipped += 1
                    continue

                signal_dict = {
                    "market_id": sig.market_ticker,
                    "market_ticker": sig.market_ticker,
                    "side": "BUY" if (sig.direction or "yes") == "yes" else "SELL",
                    "confidence": getattr(sig, "confidence", 0.0) or 0.0,
                    "size": min(50.0, bankroll * 0.03),
                    "price": getattr(sig, "model_probability", 0.5) or 0.5,
                    "token_id": token_id,
                }
                result = await trader.execute_signal(
                    signal_dict,
                    bankroll=bankroll,
                    current_exposure=current_exposure,
                )
                if result.executed:
                    from backend.core.strategy_executor import execute_decision

                    trade_size = min(50.0, (bankroll or 100.0) * 0.03)
                    decision = {
                        "market_ticker": sig.market_ticker,
                        "direction": sig.direction or "yes",
                        "size": trade_size,
                        "entry_price": getattr(sig, "model_probability", 0.5) or 0.5,
                        "edge": getattr(sig, "edge", 0.0) or 0.0,
                        "confidence": getattr(sig, "confidence", 0.0) or 0.0,
                        "model_probability": getattr(sig, "model_probability", None),
                        "token_id": token_id,
                        "platform": "polymarket",
                    }
                    exec_result = await execute_decision(decision, "auto_trader", db=db)
                    if exec_result is not None:
                        sig.executed = True
                        executed += 1
                        current_exposure += trade_size
                elif result.pending_approval:
                    queued += 1
                else:
                    # Signal was rejected — mark executed so it's not
                    # re-processed every cycle.
                    sig.executed = True
                    skipped += 1
            db.commit()
            log_event(
                "info",
                f"AutoTrader cycle: executed={executed} queued={queued} skipped={skipped}",
            )
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
        pending = db.query(Trade).filter(Trade.settled.is_(False)).count()

        if state is None:
            log_event("warning", "Heartbeat: Bot state not initialized")
            return

        log_event(
            "data",
            f"Heartbeat: {pending} pending trades, bankroll: ${state.bankroll:.2f}",
            {
                "pending_trades": pending,
                "bankroll": state.bankroll,
                "is_running": state.is_running,
            },
        )
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
        config = (
            db.query(StrategyConfig)
            .filter(
                StrategyConfig.strategy_name == strategy_name,
                StrategyConfig.enabled.is_(True),
            )
            .first()
        )

        if not config:
            log_event(
                "info", f"Strategy {strategy_name} disabled or not configured, skipping"
            )
            return

        strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
        if not strategy_cls:
            log_event(
                "warning",
                f"Strategy {strategy_name} not in registry — updating heartbeat anyway",
            )
            from backend.core.heartbeat import update_heartbeat

            update_heartbeat(strategy_name)
            return

        params = {}
        if config.params:
            try:
                params = json.loads(config.params)
            except Exception:
                pass

        from backend.strategies.base import StrategyContext
        from backend.config import settings as _settings

        effective_mode = (
            config.trading_mode if config.trading_mode else _settings.TRADING_MODE
        )

        ctx = StrategyContext(
            db=db,
            clob=None,
            settings=_settings,
            logger=logger,
            params=params,
            mode=effective_mode,
        )

        strategy = strategy_cls()
        result = await strategy.run(ctx)

        from backend.core.strategy_executor import execute_decisions as _exec_decisions

        buy_decisions = [
            d
            for d in getattr(result, "decisions", [])
            if isinstance(d, dict)
            and d.get("decision") == "BUY"
            and d.get("market_ticker")
        ]

        execution_modes = []
        if effective_mode == "live":
            execution_modes = ["paper", "live"]
            logger.info(
                f"[{strategy_name}] effective_mode=live, will execute in BOTH paper+live modes"
            )
        elif effective_mode == "paper":
            execution_modes = ["paper"]
            logger.info(
                f"[{strategy_name}] effective_mode=paper, will execute in paper mode only"
            )
        elif effective_mode == "testnet":
            execution_modes = ["testnet"]
            logger.info(
                f"[{strategy_name}] effective_mode=testnet, will execute in testnet mode only"
            )
        else:
            execution_modes = [_settings.TRADING_MODE]
            logger.warning(
                f"[{strategy_name}] Unknown effective_mode={effective_mode}, falling back to {_settings.TRADING_MODE}"
            )

        for mode in execution_modes:
            logger.info(
                f"[{strategy_name}] Preparing to execute {len(buy_decisions)} decisions in {mode} mode"
            )
            if buy_decisions:
                decisions_copy = [d.copy() for d in buy_decisions]
                for d in decisions_copy:
                    d["trading_mode"] = mode
                logger.info(
                    f"[{strategy_name}] Calling _exec_decisions with {len(decisions_copy)} decisions, mode={mode}"
                )
                trade_results = await _exec_decisions(
                    decisions_copy, strategy_name, db=db
                )
                result.trades_placed += len(trade_results)
                logger.info(
                    f"[{strategy_name}] PARALLEL: executed {len(trade_results)} trades in {mode} mode (input decisions: {len(decisions_copy)})"
                )
            else:
                logger.info(f"[{strategy_name}] No buy_decisions to execute")

        from backend.core.heartbeat import update_heartbeat

        log_event(
            "info",
            f"Strategy {strategy_name} cycle done: decisions={result.decisions_recorded} trades={result.trades_placed} errors={len(result.errors)}",
        )

    except Exception as e:
        log_event("error", f"Strategy cycle job failed for {strategy_name}: {e}")
        logger.exception(f"strategy_cycle_job({strategy_name})")
    finally:
        db.close()

    # Heartbeat AFTER db.close() so the pool connection is returned first
    try:
        update_heartbeat(strategy_name)
    except Exception:
        pass
