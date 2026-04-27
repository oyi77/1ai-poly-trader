"""FastAPI backend for BTC 5-min trading bot dashboard."""

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Header,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional, AsyncGenerator
from contextlib import asynccontextmanager
import asyncio
import os
import time
import signal
import sys
from collections import deque

from backend.config import settings
from backend.models.database import (
    get_db,
    init_db,
    SessionLocal,
    Signal,
    Trade,
    BotState,
    AILog,
    StrategyConfig,
    MarketWatch,
    WalletConfig,
    DecisionLog,
    TradeContext,
)

# Wallet creation support
try:
    from eth_account import Account
except ImportError:
    Account = None
    import logging

    logging.getLogger("trading_bot").warning(
        "eth_account not available - wallet creation disabled"
    )
from backend.core.signals import scan_for_signals, TradingSignal
from backend.data.btc_markets import fetch_active_btc_markets
from backend.data.crypto import fetch_crypto_price, compute_btc_microstructure
from backend.core.errors import handle_errors
from backend.core.event_bus import event_bus, publish_event
from backend.api.ws_manager_v2 import topic_manager
from backend.api.connection_limits import connection_limiter
from backend.api.auth import router as auth_router, require_admin
from backend.api.markets import router as markets_router, _weather_signal_to_response
from backend.api.trading import (
    router as trading_router,
    _signal_to_response,
    _compute_calibration_summary,
    CalibrationSummary,
    CalibrationBucket,
    SignalResponse,
    TradeResponse,
)
from backend.api.copy_trading import router as copy_trading_router
from backend.api.arbitrage import router as arbitrage_router
from backend.api.market_intel import router as market_intel_router
from backend.api.auto_trader import router as auto_trader_router
from backend.api.system import router as system_router, get_stats, BotStats
from backend.api.backtest import router as backtest_router
from backend.api.wallets import router as wallets_router
from backend.api.analytics import router as analytics_router
from backend.api.settings import router as settings_router
from backend.api.activities import router as activities_router
from backend.api.proposals import router as proposals_router
from backend.api.admin import router as admin_router
from backend.api.brain import router as brain_router
from backend.api.errors import router as errors_router
from backend.api.metrics_endpoint import router as metrics_router
from backend.api.alerts import router as alerts_router
from backend.core.wallet_reconciliation import WalletReconciler

# HFT shared data service
from backend.data.shared_service import router as shared_data_router

from pydantic import BaseModel
from fastapi import BackgroundTasks
import logging

logger = logging.getLogger("trading_bot")

_STRATEGY_DEFAULTS = [
    (
        "copy_trader",
        True,
        60,
        {"max_wallets": 20, "min_score": 60.0, "poll_interval": 60},
    ),
    (
        "weather_emos",
        True,
        300,
        {"min_edge": 0.05, "max_position_usd": 100, "calibration_window_days": 40},
    ),
    ("kalshi_arb", True, 60, {"min_edge": 0.02, "allow_live_execution": False}),
    ("btc_oracle", True, 30, {"min_edge": 0.03, "max_minutes_to_resolution": 10}),
    ("btc_5m", False, 60, {}),
    ("btc_momentum", True, 60, {"max_trade_fraction": 0.03}),
    (
        "general_scanner",
        True,
        300,
        {"min_volume": 50000, "min_edge": 0.05, "max_position_usd": 150},
    ),
    (
        "bond_scanner",
        True,
        600,
        {"min_price": 0.92, "max_price": 0.98, "max_position_usd": 200},
    ),
    ("realtime_scanner", True, 60, {"min_edge": 0.03, "max_position_usd": 100}),
    (
        "whale_pnl_tracker",
        True,
        120,
        {"min_wallet_pnl": 10000, "max_position_usd": 100},
    ),
    ("market_maker", False, 30, {"spread": 0.02, "max_position_usd": 200}),
]


def _seed_strategy_configs() -> None:
    import json as _json

    db = SessionLocal()
    try:
        added = 0
        for name, enabled, interval, params in _STRATEGY_DEFAULTS:
            exists = (
                db.query(StrategyConfig)
                .filter(StrategyConfig.strategy_name == name)
                .first()
            )
            if not exists:
                db.add(
                    StrategyConfig(
                        strategy_name=name,
                        enabled=enabled,
                        interval_seconds=interval,
                        params=_json.dumps(params),
                    )
                )
                added += 1
        if added:
            db.commit()
            logger.info(f"Seeded {added} strategy configs into database")
    finally:
        db.close()


class GracefulShutdownHandler:
    """Handles graceful shutdown on SIGTERM/SIGINT with timeout."""
    
    def __init__(self, app: FastAPI):
        self.app = app
        self.shutdown_event = asyncio.Event()
        self.shutdown_timeout = 30.0
        self.start_time = None
        
    def _signal_handler(self, signum, frame):
        """Signal handler for SIGTERM and SIGINT."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name} signal, initiating graceful shutdown...")
        self.start_time = time.time()
        self.shutdown_event.set()
    
    def register_handlers(self):
        """Register signal handlers for SIGTERM and SIGINT."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        logger.info("Signal handlers registered for SIGTERM and SIGINT")
    
    async def wait_for_shutdown(self):
        """Wait for shutdown signal or timeout."""
        try:
            await asyncio.wait_for(
                self.shutdown_event.wait(),
                timeout=self.shutdown_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Shutdown timeout ({self.shutdown_timeout}s) reached")
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time since shutdown started."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # --- Startup ---
    from datetime import datetime as _dt, timezone as _tz
    from backend.core.task_manager import TaskManager

    app.state.start_time = _dt.now(_tz.utc)
    app.state.task_manager = TaskManager()
    
    logger.info("Initializing connection limiter...")
    await connection_limiter.initialize_redis(settings.REDIS_URL if settings.REDIS_ENABLED else None)
    app.state.connection_limiter = connection_limiter
    
    # Initialize graceful shutdown handler
    shutdown_handler = GracefulShutdownHandler(app)
    shutdown_handler.register_handlers()
    app.state.shutdown_handler = shutdown_handler
    
    from backend.api_websockets import brain_stream, activity_stream, proposals
    brain_stream.set_task_manager(app.state.task_manager)
    activity_stream.set_task_manager(app.state.task_manager)
    proposals.set_task_manager(app.state.task_manager)
    
    logger.info("=" * 60)
    logger.info("BTC 5-MIN TRADING BOT v3.0")
    logger.info("=" * 60)
    logger.info("Initializing database...")

    init_db()
    
    logger.info("Seeding initial settings...")
    try:
        from backend.scripts.seed_settings import seed_settings
        if seed_settings():
            logger.info("  - Settings table seeded with defaults")
        else:
            logger.info("  - Settings already exist or table not found")
    except Exception as e:
        logger.warning(f"Failed to seed settings: {e}", exc_info=True)
    
    logger.info("Initializing settings cache...")
    try:
        from backend.core.config_service import reload_settings_from_db
        db = SessionLocal()
        try:
            count = reload_settings_from_db(db)
            logger.info(f"  - Loaded {count} settings into cache")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to initialize settings cache: {e}", exc_info=True)

    db = SessionLocal()
    try:
        state = db.query(BotState).first()
        if not state:
            state = BotState(
                bankroll=settings.INITIAL_BANKROLL,
                paper_bankroll=settings.INITIAL_BANKROLL,
                total_trades=0,
                winning_trades=0,
                total_pnl=0.0,
                is_running=True,
            )
            db.add(state)
            db.commit()
            logger.info(
                f"Created new bot state with ${settings.INITIAL_BANKROLL:,.2f} bankroll"
            )
        else:
            state.is_running = True
            db.commit()
            logger.info(
                f"Loaded bot state: Bankroll ${state.bankroll:,.2f}, P&L ${state.total_pnl:+,.2f}, {state.total_trades} trades"
            )
    finally:
        db.close()

    logger.info("")
    logger.info("Configuration:")
    logger.info(f"  - Simulation mode: {settings.SIMULATION_MODE}")
    logger.info(f"  - Min edge threshold: {settings.MIN_EDGE_THRESHOLD:.0%}")
    logger.info(f"  - Kelly fraction: {settings.KELLY_FRACTION:.0%}")
    logger.info(f"  - Scan interval: {settings.SCAN_INTERVAL_SECONDS}s")
    logger.info(f"  - Settlement interval: {settings.SETTLEMENT_INTERVAL_SECONDS}s")
    logger.info("")

    # Load all strategies BEFORE starting scheduler
    from backend.strategies.registry import load_all_strategies

    logger.info("Loading trading strategies...")
    load_all_strategies()
    logger.info(
        f"  - Strategies loaded: {', '.join(sorted(__import__('backend.strategies.registry', fromlist=['STRATEGY_REGISTRY']).STRATEGY_REGISTRY.keys()))}"
    )

    _seed_strategy_configs()

    # Register ModeExecutionContext for each active mode (paper/testnet/live)
    # Required by auto_trader and strategy_executor to execute trades
    try:
        from backend.core.mode_context import ModeExecutionContext, register_context
        from backend.core.risk_manager import RiskManager
        from backend.data.polymarket_clob import clob_from_settings

        for mode in ["paper", "testnet", "live"]:
            if not settings.is_mode_active(mode) and mode != "paper":
                continue
            try:
                clob_client = clob_from_settings(mode=mode)
            except Exception:
                clob_client = None
            risk_manager = RiskManager()
            strategy_configs = {}
            configs = db.query(StrategyConfig).filter(
                (StrategyConfig.mode == mode) | (StrategyConfig.mode == None)
            ).all()
            for config in configs:
                strategy_configs[config.strategy_name] = config
            context = ModeExecutionContext(
                mode=mode,
                clob_client=clob_client,
                risk_manager=risk_manager,
                strategy_configs=strategy_configs,
            )
            register_context(mode, context)
            logger.info(f"ModeExecutionContext registered for mode: {mode} with {len(strategy_configs)} strategies")
    except Exception as e:
        logger.warning(f"Failed to register mode contexts: {e}", exc_info=True)

    logger.info("Starting wallet reconciliation recovery...")
    try:
        from backend.data.polymarket_clob import clob_from_settings
        
        db = SessionLocal()
        try:
            # Only reconcile live mode — there is no separate testnet blockchain,
            # so reconciling "testnet" re-imports the same live positions with mode=testnet.
            for mode in ["live"]:
                if settings.TRADING_MODE in ("live", "paper"):
                    try:
                        clob = clob_from_settings(mode=mode)
                        reconciler = WalletReconciler(clob, db, mode)
                        result = await reconciler.full_reconciliation()
                        
                        state = db.query(BotState).first()
                        if state:
                            state.last_sync_at = result.last_sync_at
                            db.commit()
                        
                        logger.info(
                            f"Startup recovery [{mode}]: imported={result.imported_count}, "
                            f"updated={result.updated_count}, closed={result.closed_count}, "
                            f"errors={len(result.errors)}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[api.main.lifespan] {type(e).__name__}: Startup recovery [{mode}] failed: {e}",
                            exc_info=True
                        )
        finally:
            db.close()
    except Exception as e:
        logger.warning(
            f"[api.main.lifespan] {type(e).__name__}: Wallet reconciliation startup failed: {e}",
            exc_info=True
        )

    from backend.core.scheduler import start_scheduler, log_event

    start_scheduler()
    log_event("success", "BTC 5-min trading bot initialized")

    logger.info("Bot is now running!")
    logger.info(
        f"  - BTC scan: every {settings.SCAN_INTERVAL_SECONDS}s (edge >= {settings.MIN_EDGE_THRESHOLD:.0%})"
    )
    logger.info(f"  - Settlement check: every {settings.SETTLEMENT_INTERVAL_SECONDS}s")
    if settings.WEATHER_ENABLED:
        logger.info(
            f"  - Weather scan: every {settings.WEATHER_SCAN_INTERVAL_SECONDS}s (edge >= {settings.WEATHER_MIN_EDGE_THRESHOLD:.0%})"
        )
        logger.info(f"  - Weather cities: {settings.WEATHER_CITIES}")
    else:
        logger.info("  - Weather trading: DISABLED")
    logger.info("=" * 60)

    _balance_cache = {"balance": None, "timestamp": 0, "mode": settings.TRADING_MODE}

    async def refresh_balance_cache():
        if settings.TRADING_MODE not in ("live", "testnet"):
            return

        try:
            from backend.data.polymarket_clob import clob_from_settings

            clob = clob_from_settings()
            async with clob:
                await clob.create_or_derive_api_creds()
                balance_data = await clob.get_wallet_balance()
                clob_balance = balance_data.get("usdc_balance", 0.0)

                if clob_balance >= 0:
                    _balance_cache["balance"] = clob_balance
                    _balance_cache["timestamp"] = time.time()
                    _balance_cache["mode"] = settings.TRADING_MODE
                    logger.info(f"Balance cache refreshed: ${clob_balance:.2f}")
        except Exception as e:
            logger.warning(
                f"[api.main.refresh_balance_cache] {type(e).__name__}: Failed to refresh balance cache: {e}",
                exc_info=True
            )

    async def stats_broadcaster():
        logger.info("Stats broadcaster task started")

        await refresh_balance_cache()

        BALANCE_REFRESH_INTERVAL = 30

        while True:
            try:
                connection_count = topic_manager.get_topic_subscriber_count("stats")
                if connection_count > 0:
                    logger.info(
                        f"Broadcasting stats to {connection_count} clients"
                    )

                    now = time.time()
                    if now - _balance_cache["timestamp"] > BALANCE_REFRESH_INTERVAL:
                        await refresh_balance_cache()

                    db = SessionLocal()
                    try:
                        # Get stats for all 3 modes
                        stats = await get_stats(db, None, mode=None)
                        await topic_manager.broadcast(
                            "stats",
                            {
                                "type": "stats_update",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data": stats.model_dump(mode='json'),
                            }
                        )
                    finally:
                        db.close()
                else:
                    logger.debug(f"No active WebSocket connections, skipping broadcast")
            except Exception as e:
                logger.error(
                    f"[api.main.stats_broadcaster] {type(e).__name__}: Stats broadcaster error: {e}",
                    exc_info=True
                )
            await asyncio.sleep(1)

    logger.info("Initializing Redis pub/sub for WebSocket...")
    await topic_manager.initialize_redis()
    
    logger.info("Creating stats broadcaster background task...")
    stats_task = await app.state.task_manager.create_task(
        stats_broadcaster(), name="stats_broadcaster"
    )
    logger.info("Stats broadcaster task created")

    from backend.data.polymarket_websocket import (
        get_market_websocket,
        shutdown_market_websocket,
        get_user_websocket,
        shutdown_user_websocket,
    )
    from backend.data.orderbook_cache import get_orderbook_cache

    logger.info("Starting Polymarket WebSocket for real-time market data...")
    market_ws_task = None
    user_ws_task = None
    try:
        if settings.POLYMARKET_WS_ENABLED:
            asset_ids = []
            condition_ids = []
            db = SessionLocal()
            try:
                active_markets = (
                    db.query(MarketWatch).all()
                )
                for market in active_markets:
                    if market.token_id:
                        asset_ids.append(market.token_id)
                    if market.condition_id:
                        condition_ids.append(market.condition_id)
            finally:
                db.close()

            if asset_ids:
                market_ws = await get_market_websocket(asset_ids)
                orderbook_cache = get_orderbook_cache()

                def handle_orderbook(snapshot):
                    logger.debug(f"Orderbook update: {snapshot.asset_id}")
                    
                    async def update_orderbook():
                        await app.state.task_manager.create_task(
                            orderbook_cache.update(
                                snapshot.asset_id, snapshot.bids, snapshot.asks
                            ),
                            name=f"orderbook_update_{snapshot.asset_id}"
                        )
                    
                    asyncio.create_task(update_orderbook())
                    publish_event(
                        "orderbook_update",
                        {
                            "asset_id": snapshot.asset_id,
                            "bids": snapshot.bids[:5],
                            "asks": snapshot.asks[:5],
                            "timestamp": snapshot.timestamp,
                        },
                    )

                def handle_trade(trade):
                    logger.debug(f"Trade: {trade.side} {trade.size} @ {trade.price}")
                    publish_event(
                        "trade_executed",
                        {
                            "asset_id": trade.asset_id,
                            "price": trade.price,
                            "size": trade.size,
                            "side": trade.side,
                            "timestamp": trade.timestamp,
                        },
                    )

                market_ws.on_orderbook(handle_orderbook)
                market_ws.on_trade(handle_trade)

                market_ws_task = await app.state.task_manager.create_task(
                    market_ws.connect(), name="polymarket_market_ws"
                )
                logger.info(
                    f"Polymarket WebSocket started for {len(asset_ids)} markets"
                )
            else:
                logger.info("No active markets found - WebSocket not started")

            if settings.POLYMARKET_USER_WS_ENABLED and condition_ids:
                if all(
                    [
                        settings.POLYMARKET_API_KEY,
                        settings.POLYMARKET_API_SECRET,
                        settings.POLYMARKET_API_PASSPHRASE,
                    ]
                ):
                    user_ws = await get_user_websocket(
                        condition_ids=condition_ids,
                        api_key=settings.POLYMARKET_API_KEY,
                        api_secret=settings.POLYMARKET_API_SECRET,
                        api_passphrase=settings.POLYMARKET_API_PASSPHRASE,
                    )

                    def handle_user_order(event):
                        logger.info(
                            f"Order update: {event.get('id')} - {event.get('status')}"
                        )
                        publish_event("user_order_update", event)

                    def handle_user_trade(event):
                        logger.info(
                            f"Trade fill: {event.get('id')} - {event.get('status')}"
                        )
                        publish_event("user_trade_fill", event)

                        db = SessionLocal()
                        try:
                            trade_id = event.get("id")
                            status = event.get("status")

                            if status == "CONFIRMED":
                                trade = (
                                    db.query(Trade)
                                    .filter(Trade.clob_order_id == trade_id)
                                    .first()
                                )
                                if trade and not trade.settled:
                                    trade.settled = True
                                    trade.settlement_time = datetime.now(timezone.utc)
                                    db.commit()
                                    logger.info(f"Trade {trade_id} confirmed on-chain")

                                async def refresh_task():
                                    await app.state.task_manager.create_task(
                                        refresh_balance_cache(), name="refresh_balance_cache"
                                    )
                                
                                asyncio.create_task(refresh_task())
                        except Exception as e:
                            logger.error(
                                f"[api.main.handle_user_trade] {type(e).__name__}: Error updating trade status: {e}",
                                exc_info=True
                            )
                        finally:
                            db.close()

                    user_ws.on_user_order(handle_user_order)
                    user_ws.on_user_trade(handle_user_trade)

                    user_ws_task = await app.state.task_manager.create_task(
                        user_ws.connect(), name="polymarket_user_ws"
                    )
                    logger.info(
                        f"Polymarket User WebSocket started for {len(condition_ids)} markets"
                    )
                else:
                    logger.warning("User WebSocket enabled but API credentials missing")
            else:
                logger.info("Polymarket User WebSocket disabled in settings")
        else:
            logger.info("Polymarket WebSocket disabled in settings")
    except Exception as e:
        logger.error(
            f"[api.main.lifespan] {type(e).__name__}: Failed to start Polymarket WebSocket: {e}",
            exc_info=True
        )

    try:
        from backend.core.bankroll_reconciliation import reconcile_bot_state

        db = SessionLocal()
        try:
            await reconcile_bot_state(
                db,
                modes=("live",),
                apply=True,
                commit=True,
                source="api_startup_live_reconcile",
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning(
            f"[api.main.lifespan] {type(e).__name__}: Live bankroll startup reconciliation failed: {e}",
            exc_info=True,
        )

    yield

    shutdown_handler = getattr(app.state, 'shutdown_handler', None)
    shutdown_start = time.time()
    
    logger.info("=" * 60)
    logger.info("GRACEFUL SHUTDOWN SEQUENCE INITIATED")
    logger.info("=" * 60)
    
    try:
        logger.info("1. Stopping new request acceptance...")
        app.state.shutting_down = True
        logger.info("   ✓ New requests blocked")
        
        logger.info("2. Waiting for active requests to complete (max 5s)...")
        active_requests = getattr(app.state, 'active_requests', 0)
        wait_start = time.time()
        while active_requests > 0 and (time.time() - wait_start) < 5.0:
            await asyncio.sleep(0.1)
            active_requests = getattr(app.state, 'active_requests', 0)
        if active_requests > 0:
            logger.warning(f"   ⚠ {active_requests} active requests still pending after 5s")
        else:
            logger.info("   ✓ All active requests completed")
        
        logger.info("3. Closing WebSocket connections...")
        ws_count = len(ws_manager.active_connections)
        for ws in ws_manager.active_connections[:]:
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
        logger.info(f"   ✓ Closed {ws_count} WebSocket connections")
        
        logger.info("4. Shutting down Redis pub/sub...")
        try:
            await topic_manager.shutdown_redis()
            logger.info("   ✓ Redis pub/sub shut down")
        except Exception as e:
            logger.warning(f"   ⚠ Error shutting down Redis: {e}")
        
        logger.info("5. Shutting down connection limiter...")
        try:
            await connection_limiter.shutdown()
            logger.info("   ✓ Connection limiter shut down")
        except Exception as e:
            logger.warning(f"   ⚠ Error shutting down connection limiter: {e}")
        
        logger.info("6. Shutting down Polymarket WebSocket...")
        if market_ws_task:
            try:
                await shutdown_market_websocket()
                market_ws_task.cancel()
                try:
                    await market_ws_task
                except asyncio.CancelledError:
                    pass
                logger.info("   ✓ Polymarket market WebSocket shut down")
            except Exception as e:
                logger.warning(f"   ⚠ Error shutting down market WebSocket: {e}")

        if user_ws_task:
            try:
                await shutdown_user_websocket()
                user_ws_task.cancel()
                try:
                    await user_ws_task
                except asyncio.CancelledError:
                    pass
                logger.info("   ✓ Polymarket user WebSocket shut down")
            except Exception as e:
                logger.warning(f"   ⚠ Error shutting down user WebSocket: {e}")

        logger.info("7. Shutting down TaskManager...")
        try:
            task_count = len(app.state.task_manager.tasks)
            await app.state.task_manager.shutdown()
            logger.info(f"   ✓ TaskManager shut down ({task_count} tasks cancelled)")
        except Exception as e:
            logger.warning(f"   ⚠ Error shutting down TaskManager: {e}")

        logger.info("8. Stopping scheduler...")
        try:
            from backend.core.scheduler import stop_scheduler
            stop_scheduler()
            logger.info("   ✓ Scheduler stopped")
        except Exception as e:
            logger.warning(f"   ⚠ Error stopping scheduler: {e}")

        logger.info("9. Waiting for in-flight jobs (max 3s)...")
        await asyncio.sleep(3.0)
        logger.info("   ✓ Grace period complete")

        logger.info("10. Closing database connections...")
        try:
            from backend.models.database import engine
            engine.dispose()
            logger.info("   ✓ Database connections closed")
        except Exception as e:
            logger.warning(f"   ⚠ Error closing database: {e}")

    except Exception as e:
        logger.error(
            f"[api.main.lifespan] {type(e).__name__}: Error during shutdown sequence: {e}",
            exc_info=True
        )
    
    elapsed = time.time() - shutdown_start
    logger.info("=" * 60)
    logger.info(f"SHUTDOWN COMPLETE (took {elapsed:.1f}s)")
    logger.info("=" * 60)
    
    sys.exit(0)


app = FastAPI(
    title="BTC 5-Min Trading Bot",
    description="Polymarket BTC Up/Down 5-minute market trading bot",
    version="3.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.api.rate_limiter import RateLimiterMiddleware
from backend.api.versioning import APIVersionMiddleware
from backend.api.timeout_middleware import TimeoutMiddleware

app.add_middleware(TimeoutMiddleware)
app.add_middleware(RateLimiterMiddleware, requests_per_minute=100)
app.add_middleware(APIVersionMiddleware)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(markets_router, prefix="/api/v1")
app.include_router(trading_router, prefix="/api/v1")
app.include_router(copy_trading_router, prefix="/api/v1")
app.include_router(arbitrage_router, prefix="/api/v1")
app.include_router(market_intel_router, prefix="/api/v1")
app.include_router(auto_trader_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
app.include_router(backtest_router, prefix="/api/v1")
app.include_router(wallets_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(proposals_router, prefix="/api/v1")
# Backward-compatible proposal routes for older dashboard/tests that still call
# /api/proposals while the canonical path is /api/v1/proposals.
app.include_router(proposals_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
# /api/bot/start alias for tests and older clients (canonical: /api/v1/bot/start)
app.include_router(system_router, prefix="/api")
app.include_router(brain_router, prefix="/api/v1")
app.include_router(errors_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(shared_data_router)


# Add metrics middleware for automatic tracking
@app.middleware("http")
async def metrics_middleware_wrapper(request: Request, call_next):
    from backend.monitoring.middleware import metrics_middleware

    return await metrics_middleware(request, call_next)


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.exception(
                    f"[api.main.ConnectionManager.broadcast] {type(e).__name__}: Failed to broadcast message to WebSocket connection: {e}"
                )


ws_manager = ConnectionManager()


# Pydantic response models
# Default backtest configuration values
_DEFAULT_MAX_TRADE_SIZE = 100.0
_DEFAULT_MIN_EDGE_THRESHOLD = 0.02
_DEFAULT_MARKET_TYPES = ["BTC"]
DEFAULT_SLIPPAGE_BPS = 5


class BacktestRequest(BaseModel):
    initial_bankroll: float = 1000.0
    max_trade_size: float = 100.0
    min_edge_threshold: float = 0.02
    start_date: str | None = None  # ISO format datetime
    end_date: str | None = None  # ISO format datetime
    market_types: list[str] = ["BTC", "Weather", "CopyTrader"]
    slippage_bps: int = 5  # basis points


class FrontendBacktestRequest(BaseModel):
    strategy_name: str
    start_date: str | None = None
    end_date: str | None = None
    initial_bankroll: float = 10000.0


class BtcPriceResponse(BaseModel):
    price: float
    change_24h: float
    change_7d: float
    market_cap: float
    volume_24h: float
    last_updated: datetime


class BtcWindowResponse(BaseModel):
    slug: str
    market_id: str
    up_price: float
    down_price: float
    window_start: datetime
    window_end: datetime
    volume: float
    is_active: bool
    is_upcoming: bool
    time_until_end: float
    spread: float


class MicrostructureResponse(BaseModel):
    rsi: float = 50.0
    momentum_1m: float = 0.0
    momentum_5m: float = 0.0
    momentum_15m: float = 0.0
    vwap_deviation: float = 0.0
    sma_crossover: float = 0.0
    volatility: float = 0.0
    price: float = 0.0
    source: str = "unknown"


class WeatherForecastResponse(BaseModel):
    city_key: str
    city_name: str
    target_date: str
    mean_high: float
    std_high: float
    mean_low: float
    std_low: float
    num_members: int
    ensemble_agreement: float


class WeatherMarketResponse(BaseModel):
    slug: str
    market_id: str
    platform: str = "polymarket"
    title: str
    city_key: str
    city_name: str
    target_date: str
    threshold_f: float
    metric: str
    direction: str
    yes_price: float
    no_price: float
    volume: float


class WeatherSignalResponse(BaseModel):
    market_id: str
    city_key: str
    city_name: str
    target_date: str
    threshold_f: float
    metric: str
    direction: str
    model_probability: float
    market_probability: float
    edge: float
    confidence: float
    suggested_size: float
    reasoning: str
    ensemble_mean: float
    ensemble_std: float
    ensemble_members: int
    actionable: bool = False


class DashboardData(BaseModel):
    stats: BotStats
    btc_price: Optional[BtcPriceResponse]
    microstructure: Optional[MicrostructureResponse] = None
    windows: List[BtcWindowResponse]
    active_signals: List[SignalResponse]
    recent_trades: List[TradeResponse]
    top_winning_trades: List[TradeResponse] = []
    equity_curve: List[dict]
    calibration: Optional[CalibrationSummary] = None
    weather_signals: List[WeatherSignalResponse] = []
    weather_forecasts: List[WeatherForecastResponse] = []
    trading_mode: str = "paper"


class EventResponse(BaseModel):
    timestamp: str
    type: str
    message: str
    data: dict = {}


def _serialize_trade_response(trade: Trade, contexts: dict[int, TradeContext]) -> TradeResponse:
    context = contexts.get(trade.id)
    return TradeResponse(
        id=trade.id,
        market_ticker=trade.market_ticker,
        platform=trade.platform,
        event_slug=trade.event_slug,
        direction=trade.direction,
        entry_price=trade.entry_price,
        size=trade.size,
        timestamp=trade.timestamp,
        settled=trade.settled,
        result=trade.result,
        pnl=trade.pnl,
        strategy=(context.strategy if context else None) or getattr(trade, "strategy", None),
        signal_source=(context.signal_source if context else None)
        or getattr(trade, "signal_source", None),
        confidence=(context.confidence if context else None)
        or getattr(trade, "confidence", None),
        trading_mode=trade.trading_mode,
    )


def _load_trade_contexts(db: Session, trades: list[Trade]) -> dict[int, TradeContext]:
    trade_ids = [trade.id for trade in trades]
    if not trade_ids:
        return {}
    return {
        context.trade_id: context
        for context in db.query(TradeContext).filter(TradeContext.trade_id.in_(trade_ids)).all()
    }


def _build_account_equity_curve(db: Session, curve_mode: str = "live") -> list[dict]:
    """Build dashboard equity points without letting historical backfills redefine live equity."""
    equity_curve: list[dict] = []
    initial_bankroll = 100.0 if curve_mode == "testnet" else float(settings.INITIAL_BANKROLL)
    mode_state = db.query(BotState).filter_by(mode=curve_mode).first()

    if curve_mode == "live":
        historical_trades = (
            db.query(Trade)
            .filter(
                Trade.settled.is_(True),
                Trade.trading_mode == "live",
                Trade.pnl.isnot(None),
                or_(
                    Trade.settlement_source.is_(None),
                    Trade.settlement_source != "backfill_conservative_loss",
                ),
            )
            .order_by(Trade.timestamp)
            .limit(500)
            .all()
        )
        realized_points: list[tuple[datetime, float]] = []
        cumulative_realized = 0.0
        for trade in historical_trades:
            cumulative_realized += float(trade.pnl or 0.0)
            realized_points.append((trade.timestamp, cumulative_realized))

        current_pnl = float(mode_state.total_pnl or 0.0) if mode_state else cumulative_realized
        current_bankroll = (
            float(mode_state.bankroll or initial_bankroll) if mode_state else initial_bankroll + current_pnl
        )

        if realized_points:
            final_realized = realized_points[-1][1]
            adjustment = current_pnl - final_realized
            for timestamp, realized_pnl in realized_points:
                point_pnl = realized_pnl + adjustment
                equity_curve.append(
                    {
                        "timestamp": timestamp.isoformat(),
                        "pnl": point_pnl,
                        "bankroll": current_bankroll - (current_pnl - point_pnl),
                    }
                )

        equity_curve.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pnl": current_pnl,
                "bankroll": current_bankroll,
            }
        )
        return equity_curve

    cumulative_pnl = 0.0
    equity_trades = (
        db.query(Trade)
        .filter(Trade.settled.is_(True), Trade.trading_mode == curve_mode)
        .order_by(Trade.timestamp)
        .all()
    )
    for trade in equity_trades:
        cumulative_pnl += float(trade.pnl or 0.0)
        equity_curve.append(
            {
                "timestamp": trade.timestamp.isoformat(),
                "pnl": cumulative_pnl,
                "bankroll": initial_bankroll + cumulative_pnl,
            }
        )

    if mode_state:
        if curve_mode == "paper":
            current_bankroll = mode_state.paper_bankroll if mode_state.paper_bankroll is not None else mode_state.bankroll
            current_pnl = mode_state.paper_pnl if mode_state.paper_pnl is not None else mode_state.total_pnl
        else:
            current_bankroll = mode_state.testnet_bankroll if mode_state.testnet_bankroll is not None else mode_state.bankroll
            current_pnl = mode_state.testnet_pnl if mode_state.testnet_pnl is not None else mode_state.total_pnl
        equity_curve.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pnl": float(current_pnl or 0.0),
                "bankroll": float(current_bankroll or initial_bankroll),
            }
        )

    return equity_curve


# Core endpoints
@app.get("/api/health")
async def api_health_alias(db: Session = Depends(get_db)):
    return await health_check(db)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "BTC 5-Min Trading Bot API v3.0",
        "simulation_mode": settings.SIMULATION_MODE,
    }


@app.get("/api/v1/health")
async def health_check(db: Session = Depends(get_db)):
    """Return system health including per-strategy heartbeat and dependency status."""
    checks = {}
    overall_status = "ok"

    try:
        db.execute(func.now())
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
        overall_status = "degraded"
        logger.error(
            f"[api.main.health_check] {type(e).__name__}: Database health check failed: {e}",
            exc_info=True
        )

    redis_url = getattr(settings, "JOB_QUEUE_URL", "")
    if redis_url.startswith("redis://"):
        try:
            from redis import Redis

            r = Redis.from_url(redis_url, socket_connect_timeout=2)
            r.ping()
            checks["redis"] = {"status": "ok"}
            r.close()
        except Exception as e:
            checks["redis"] = {"status": "error", "error": str(e)}
            if overall_status == "ok":
                overall_status = "degraded"
            logger.warning(
                f"[api.main.health_check] {type(e).__name__}: Redis health check failed: {e}",
                exc_info=True
            )
    else:
        checks["redis"] = {"status": "not_configured", "fallback": "sqlite"}

    try:
        from backend.data.polymarket_clob import clob_from_settings

        client = clob_from_settings()
        ok_resp = client.get_ok()
        if ok_resp:
            checks["polymarket_clob"] = {"status": "ok"}
        else:
            checks["polymarket_clob"] = {
                "status": "error",
                "error": "get_ok returned falsy",
            }
            if overall_status == "ok":
                overall_status = "degraded"
    except Exception as e:
        checks["polymarket_clob"] = {"status": "error", "error": str(e)}
        if overall_status == "ok":
            overall_status = "degraded"

    try:
        from backend.core.heartbeat import get_strategy_health

        healths = get_strategy_health(db)
        all_healthy = all(h["healthy"] or h["lag_seconds"] is None for h in healths)
        if not all_healthy and overall_status == "ok":
            overall_status = "degraded"
    except Exception as e:
        healths = []
        logger.warning(
            f"[api.main.health_check] {type(e).__name__}: Failed to get strategy health: {e}",
            exc_info=True
        )
        if overall_status == "ok":
            overall_status = "degraded"

    # 2. Redis connectivity (optional — falls back to SQLite)
    redis_url = getattr(settings, "JOB_QUEUE_URL", "")
    if redis_url.startswith("redis://"):
        try:
            from redis import Redis

            r = Redis.from_url(redis_url, socket_connect_timeout=2)
            r.ping()
            checks["redis"] = {"status": "ok"}
            r.close()
        except Exception as e:
            checks["redis"] = {"status": "error", "error": str(e)}
            # Redis failure is non-critical (SQLite fallback exists)
            if overall_status == "ok":
                overall_status = "degraded"
            logger.warning(
                f"[api.main.health_check] {type(e).__name__}: Redis health check failed (fallback available): {e}",
                exc_info=True
            )
    else:
        checks["redis"] = {"status": "not_configured", "fallback": "sqlite"}

    # 3. Polymarket CLOB connectivity
    try:
        from backend.data.polymarket_clob import clob_from_settings

        client = clob_from_settings()
        balance = client.get_wallet_balance()
        checks["polymarket_clob"] = {"status": "ok", "balance": str(balance)}
    except Exception as e:
        checks["polymarket_clob"] = {"status": "error", "error": str(e)}
        if overall_status == "ok":
            overall_status = "degraded"
        logger.warning(
            f"[api.main.health_check] {type(e).__name__}: Polymarket CLOB health check failed: {e}",
        )
    try:
        from backend.core.heartbeat import get_strategy_health

        healths = get_strategy_health(db)
        all_healthy = all(h["healthy"] or h["lag_seconds"] is None for h in healths)
        if not all_healthy and overall_status == "ok":
            overall_status = "degraded"
    except Exception as e:
        healths = []
        logger.warning(
            f"[api.main.health_check] {type(e).__name__}: Failed to get strategy health: {e}",
            exc_info=True
        )
        if overall_status == "ok":
            overall_status = "degraded"

    try:
        from backend.models.database import engine
        pool = engine.pool
        checks["db_pool"] = {
            "status": "ok",
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "queue_size": pool.size() - pool.checkedout() - pool.overflow(),
        }
    except Exception as e:
        checks["db_pool"] = {"status": "error", "error": str(e)}
        logger.warning(f"Failed to get pool stats: {e}")

    bot_state = db.query(BotState).first()
    return {
        "status": overall_status,
        "dependencies": checks,
        "strategies": healths,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bot_running": bot_state.is_running if bot_state else False,
        "trading_mode": settings.TRADING_MODE,
    }


@app.get("/metrics")
@handle_errors()
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns all trading bot metrics in Prometheus text format.
    Scrape this endpoint with Prometheus or other monitoring systems.
    """
    from backend.monitoring import get_metrics

    return get_metrics()


@app.get("/api/v1/dashboard", response_model=DashboardData)
async def get_dashboard(
    db: Session = Depends(get_db)
):
    """Get all dashboard data in one call - returns stats for all 3 modes."""
    stats = await get_stats(db=db, _=None, mode=None)

    # Fetch BTC price from microstructure first, fallback to CoinGecko
    btc_price_data = None
    micro_data = None
    try:
        micro = await compute_btc_microstructure()
        if micro:
            micro_data = MicrostructureResponse(
                rsi=micro.rsi,
                momentum_1m=micro.momentum_1m,
                momentum_5m=micro.momentum_5m,
                momentum_15m=micro.momentum_15m,
                vwap_deviation=micro.vwap_deviation,
                sma_crossover=micro.sma_crossover,
                volatility=micro.volatility,
                price=micro.price,
                source=micro.source,
            )
            btc_price_data = BtcPriceResponse(
                price=micro.price,
                change_24h=(micro.momentum_15m or 0.0) * 96,  # rough extrapolation
                change_7d=0,
                market_cap=0,
                volume_24h=0,
                last_updated=datetime.now(timezone.utc),
            )
    except Exception as e:
        logger.warning(
            f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch BTC microstructure data, falling back to CoinGecko: {e}",
            exc_info=True
        )
    if not btc_price_data:
        try:
            btc = await fetch_crypto_price("BTC")
            if btc:
                btc_price_data = BtcPriceResponse(
                    price=btc.current_price,
                    change_24h=btc.change_24h,
                    change_7d=btc.change_7d,
                    market_cap=btc.market_cap,
                    volume_24h=btc.volume_24h,
                    last_updated=btc.last_updated,
                )
        except Exception as e:
            logger.warning(
                f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch BTC price from CoinGecko: {e}",
                exc_info=True
            )

    # Fetch windows
    windows = []
    try:
        markets = await fetch_active_btc_markets()
        windows = [
            BtcWindowResponse(
                slug=m.slug,
                market_id=m.market_id,
                up_price=m.up_price,
                down_price=m.down_price,
                window_start=m.window_start,
                window_end=m.window_end,
                volume=m.volume,
                is_active=m.is_active,
                is_upcoming=m.is_upcoming,
                time_until_end=m.time_until_end,
                spread=m.spread,
            )
            for m in markets
        ]
    except Exception as e:
        logger.warning(
            f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch active BTC markets: {e}",
            exc_info=True
        )

    # Signals — return ALL signals, mark which are actionable
    signals = []
    try:
        raw_signals = await scan_for_signals()
        signals = [
            _signal_to_response(s, actionable=s.passes_threshold) for s in raw_signals
        ]
    except Exception as e:
        logger.warning(
            f"[api.main.get_dashboard] {type(e).__name__}: Failed to scan for trading signals: {e}",
            exc_info=True
        )

    # Recent trades (with TradeContext enrichment)
    trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(50).all()
    contexts = _load_trade_contexts(db, trades)
    recent_trades = [_serialize_trade_response(t, contexts) for t in trades]

    top_winning_trade_rows = (
        db.query(Trade)
        .filter(
            Trade.settled.is_(True),
            Trade.pnl.isnot(None),
            Trade.pnl > 0,
        )
        .order_by(Trade.pnl.desc(), Trade.timestamp.desc())
        .limit(5)
        .all()
    )
    top_winning_contexts = _load_trade_contexts(db, top_winning_trade_rows)
    top_winning_trades = [
        _serialize_trade_response(t, top_winning_contexts) for t in top_winning_trade_rows
    ]

    # Equity curve: match the default dashboard/account view.  The dashboard
    # cards default to the consolidated live account-equity cache even while
    # the bot is actively running in paper mode, so the chart must not render a
    # separate paper-only loss curve beside live/all-mode account totals.
    curve_mode = "live"
    equity_curve = _build_account_equity_curve(db, curve_mode=curve_mode)

    # Calibration summary
    calibration = _compute_calibration_summary(db)

    # Weather data (if enabled)
    weather_signals_data = []
    weather_forecasts_data = []
    if settings.WEATHER_ENABLED:
        try:
            from backend.core.weather_signals import scan_for_weather_signals
            from backend.data.weather import fetch_ensemble_forecast, CITY_CONFIG

            wx_signals = await scan_for_weather_signals(mode=settings.TRADING_MODE)
            weather_signals_data = [
                WeatherSignalResponse(**_weather_signal_to_response(s).model_dump())
                for s in wx_signals
            ]

            city_keys = [
                c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()
            ]
            for city_key in city_keys:
                if city_key not in CITY_CONFIG:
                    continue
                forecast = await fetch_ensemble_forecast(city_key)
                if forecast:
                    weather_forecasts_data.append(
                        WeatherForecastResponse(
                            city_key=forecast.city_key,
                            city_name=forecast.city_name,
                            target_date=forecast.target_date.isoformat(),
                            mean_high=forecast.mean_high,
                            std_high=forecast.std_high,
                            mean_low=forecast.mean_low,
                            std_low=forecast.std_low,
                            num_members=forecast.num_members,
                            ensemble_agreement=forecast.ensemble_agreement,
                        )
                    )
        except Exception as e:
            logger.warning(
                f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch weather forecasts data: {e}",
                exc_info=True
            )

    return DashboardData(
        stats=stats,
        btc_price=btc_price_data,
        microstructure=micro_data,
        windows=windows,
        active_signals=signals,
        recent_trades=recent_trades,
        top_winning_trades=top_winning_trades,
        equity_curve=equity_curve,
        calibration=calibration,
        weather_signals=weather_signals_data,
        weather_forecasts=weather_forecasts_data,
        trading_mode=settings.TRADING_MODE,
    )


# =========================================================================
# Copy Trader endpoints
# =========================================================================


class ScoredTraderResponse(BaseModel):
    wallet: str
    pseudonym: str
    profit_30d: float
    win_rate: float
    total_trades: int
    unique_markets: int
    estimated_bankroll: float
    score: float
    market_diversity: float


class CopySignalResponse(BaseModel):
    source_wallet: str
    our_side: str
    our_outcome: str
    our_size: float
    market_price: float
    trader_score: float
    reasoning: str
    condition_id: str
    title: str
    timestamp: str


# =========================================================================
# Sync Status Endpoints
# =========================================================================


class SyncStatusResponse(BaseModel):
    """Status of wallet sync for a single mode (testnet or live)."""
    mode: str  # "testnet" or "live"
    last_synced_at: Optional[datetime]
    next_sync_at: Optional[datetime]
    last_result: Optional[str]  # "success", "error", or None
    status: str  # "healthy" if last sync < 2 min ago, else "stale"


class SyncStatusAllResponse(BaseModel):
    """Combined sync status for both modes."""
    testnet: SyncStatusResponse
    live: SyncStatusResponse


@app.get("/api/v1/admin/sync-status", response_model=SyncStatusAllResponse)
async def get_sync_status(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    """
    Get wallet sync status for testnet and live modes.
    
    Returns:
    - last_synced_at: Timestamp of last successful sync
    - next_sync_at: Estimated next sync time (if scheduled)
    - last_result: Result of last sync ("success" or error message)
    - status: "healthy" if last sync < 2 min ago, else "stale"
    """
    state = db.query(BotState).first()
    now = datetime.now(timezone.utc)
    
    # Helper to compute status
    def compute_status(last_sync_at: Optional[datetime]) -> str:
        if not last_sync_at:
            return "stale"
        # Make last_sync_at timezone-aware if it's naive
        if last_sync_at.tzinfo is None:
            last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)
        elapsed = (now - last_sync_at).total_seconds()
        return "healthy" if elapsed < 120 else "stale"
    
    # For now, use the single last_sync_at from BotState for both modes
    # In future, could track per-mode sync times
    testnet_status = SyncStatusResponse(
        mode="testnet",
        last_synced_at=state.last_sync_at if state else None,
        next_sync_at=None,  # Not scheduled yet
        last_result=None,
        status=compute_status(state.last_sync_at if state else None),
    )
    
    live_status = SyncStatusResponse(
        mode="live",
        last_synced_at=state.last_sync_at if state else None,
        next_sync_at=None,  # Not scheduled yet
        last_result=None,
        status=compute_status(state.last_sync_at if state else None),
    )
    
    return SyncStatusAllResponse(testnet=testnet_status, live=live_status)


async def _sync_wallet_background(mode: str, db: Session):
    """Background task to perform wallet sync."""
    try:
        from backend.data.polymarket_clob import clob_from_settings
        
        logger.info(f"Starting background sync for mode={mode}")
        
        clob = clob_from_settings(mode=mode)
        reconciler = WalletReconciler(clob, db, mode)
        result = await reconciler.full_reconciliation()
        
        # Update BotState with sync result
        state = db.query(BotState).first()
        if state:
            state.last_sync_at = result.last_sync_at
            db.commit()
        
        logger.info(
            f"Background sync complete [{mode}]: imported={result.imported_count}, "
            f"updated={result.updated_count}, closed={result.closed_count}, "
            f"errors={len(result.errors)}"
        )
        
        # Publish event for dashboard
        publish_event("sync_completed", {
            "mode": mode,
            "imported": result.imported_count,
            "updated": result.updated_count,
            "closed": result.closed_count,
            "errors": len(result.errors),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
    except Exception as e:
        logger.error(
            f"[api.main._sync_wallet_background] {type(e).__name__}: Background sync failed for mode={mode}: {e}",
            exc_info=True
        )
        publish_event("sync_failed", {
            "mode": mode,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


@app.post("/api/admin/sync-now")
async def sync_now(
    mode: str = "live",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    """
    Trigger an immediate wallet sync in the background.
    
    Args:
        mode: "testnet" or "live" (default: "live")
    
    Returns:
        202 Accepted with status "syncing"
    
    Note:
        - Does not block the API response
        - Sync completion is published via WebSocket events
        - Paper mode is skipped (returns 400)
    """
    if mode != "live":
        raise HTTPException(
            status_code=400,
            detail="mode must be 'live' (no separate testnet blockchain exists)"
        )
    
    if settings.TRADING_MODE == "paper":
        raise HTTPException(
            status_code=400,
            detail="Sync not available in paper mode"
        )
    
    # Queue background task
    background_tasks.add_task(_sync_wallet_background, mode, db)
    
    logger.info(f"Queued background sync for mode={mode}")
    
    return {
        "status": "syncing",
        "mode": mode,
        "message": f"Wallet sync started for {mode} mode"
    }


@app.get("/api/events/stream")
async def events_stream(request: Request, token: str = ""):
    """Server-Sent Events stream for real-time trade notifications."""
    if settings.ADMIN_API_KEY and token and token != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from fastapi.responses import StreamingResponse
    import json as _json

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    event_bus.subscribe(queue)

    async def generate() -> AsyncGenerator[str, None]:
        # Send recent history on connect
        for event in event_bus.get_history():
            yield f"data: {_json.dumps(event)}\n\n"
        # Send connected heartbeat immediately
        yield f"data: {_json.dumps({'type': 'connected', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {_json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # heartbeat keepalive
                    yield f": keepalive\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": ", ".join(origins) if origins else "*",
             "Access-Control-Allow-Headers": "*",
             "Access-Control-Allow-Methods": "GET, OPTIONS",
        },
    )


@app.get("/api/v1/events/stream")
async def events_stream_v1(request: Request, token: str = ""):
    return await events_stream(request, token)

@app.websocket("/ws/markets")
async def ws_markets(websocket: WebSocket, token: str = ""):
    """WebSocket endpoint for live market price updates."""
    if settings.ADMIN_API_KEY and token and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    allowed, error_msg = await connection_limiter.check_ws_limit(websocket)
    if not allowed:
        await websocket.close(code=1008, reason=error_msg)
        return
    
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        if data.get("action") == "subscribe":
            topic = data.get("topic", "markets")
            await topic_manager.subscribe(websocket, topic)
            await websocket.send_json({"type": "subscribed", "topic": topic})
        
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        await topic_manager.disconnect(websocket)
    except Exception as e:
        logger.exception(
            f"[api.main.ws_markets] {type(e).__name__}: Market WebSocket error: {e}"
        )
        await topic_manager.disconnect(websocket)
    finally:
        await connection_limiter.release_ws_connection(websocket)


@app.websocket("/ws/whales")
async def ws_whales(websocket: WebSocket, token: str = ""):
    """WebSocket endpoint for whale trade notifications."""
    if settings.ADMIN_API_KEY and token and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    allowed, error_msg = await connection_limiter.check_ws_limit(websocket)
    if not allowed:
        await websocket.close(code=1008, reason=error_msg)
        return
    
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        if data.get("action") == "subscribe":
            topic = data.get("topic", "whales")
            await topic_manager.subscribe(websocket, topic)
            await websocket.send_json({"type": "subscribed", "topic": topic})
        
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        await topic_manager.disconnect(websocket)
    except Exception as e:
        logger.exception(
            f"[api.main.ws_whales] {type(e).__name__}: Whale WebSocket error: {e}"
        )
        await topic_manager.disconnect(websocket)
    finally:
        await connection_limiter.release_ws_connection(websocket)


@app.websocket("/ws/activities")
async def ws_activities(websocket: WebSocket, token: str = ""):
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    allowed, error_msg = await connection_limiter.check_ws_limit(websocket)
    if not allowed:
        await websocket.close(code=1008, reason=error_msg)
        return
    
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        if data.get("action") == "subscribe":
            topic = data.get("topic", "activities")
            await topic_manager.subscribe(websocket, topic)
            await websocket.send_json({"type": "subscribed", "topic": topic})
        
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        await topic_manager.disconnect(websocket)
    except Exception as e:
        logger.exception(f"[api.main.ws_activities] {type(e).__name__}: Activity WebSocket error: {e}")
        await topic_manager.disconnect(websocket)
    finally:
        await connection_limiter.release_ws_connection(websocket)


@app.websocket("/ws/brain")
async def ws_brain(websocket: WebSocket, token: str = ""):
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    allowed, error_msg = await connection_limiter.check_ws_limit(websocket)
    if not allowed:
        await websocket.close(code=1008, reason=error_msg)
        return
    
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        if data.get("action") == "subscribe":
            topic = data.get("topic", "brain")
            await topic_manager.subscribe(websocket, topic)
            await websocket.send_json({"type": "subscribed", "topic": topic})
        
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        await topic_manager.disconnect(websocket)
    except Exception as e:
        logger.exception(f"[api.main.ws_brain] {type(e).__name__}: Brain WebSocket error: {e}")
        await topic_manager.disconnect(websocket)
    finally:
        await connection_limiter.release_ws_connection(websocket)


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, token: str = ""):
    if settings.ADMIN_API_KEY and token and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    allowed, error_msg = await connection_limiter.check_ws_limit(websocket)
    if not allowed:
        await websocket.close(code=1008, reason=error_msg)
        return
    
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        if data.get("action") == "subscribe":
            topic = data.get("topic", "events")
            await topic_manager.subscribe(websocket, topic)
            
            await websocket.send_json(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "subscribed",
                    "topic": topic,
                    "message": "Connected to BTC trading bot",
                }
            )

            from backend.core.scheduler import get_recent_events

            for event in get_recent_events(20):
                await websocket.send_json(event)

            last_event_count = len(get_recent_events(200))
            while True:
                await asyncio.sleep(2)

                current_events = get_recent_events(200)
                if len(current_events) > last_event_count:
                    new_events = current_events[last_event_count - len(current_events) :]
                    for event in new_events:
                        await websocket.send_json(event)
                    last_event_count = len(current_events)

                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

    except WebSocketDisconnect:
        await topic_manager.disconnect(websocket)
    except Exception as e:
        logger.exception(
            f"[api.main.websocket_events] {type(e).__name__}: Events WebSocket error: {e}"
        )
        await topic_manager.disconnect(websocket)
    finally:
        await connection_limiter.release_ws_connection(websocket)


@app.websocket("/ws/dashboard-data")
async def websocket_stats(websocket: WebSocket, token: str = ""):
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    allowed, error_msg = await connection_limiter.check_ws_limit(websocket)
    if not allowed:
        await websocket.close(code=1008, reason=error_msg)
        return

    await websocket.accept()

    try:
        data = await websocket.receive_json()
        if data.get("action") == "subscribe":
            topic = data.get("topic", "stats")
            await topic_manager.subscribe(websocket, topic)
            await websocket.send_json({"type": "subscribed", "topic": topic})
        
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        logger.info("Stats WebSocket disconnected")
        await topic_manager.disconnect(websocket)
    except Exception as e:
        logger.exception(
            f"[api.main.websocket_stats] {type(e).__name__}: Stats WebSocket error: {e}"
        )
        await topic_manager.disconnect(websocket)
    finally:
        await connection_limiter.release_ws_connection(websocket)


if __name__ == "__main__":
    import uvicorn
    from backend.core.config_service import get_setting

    uvicorn.run(app, host="0.0.0.0", port=int(get_setting("PORT", default="8100")))
