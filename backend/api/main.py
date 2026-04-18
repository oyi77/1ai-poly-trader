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
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional, AsyncGenerator
from contextlib import asynccontextmanager
import asyncio
import os
import time
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
from backend.api.ws_manager import (
    market_ws,
    whale_ws,
    broadcast_market_tick,
    broadcast_whale_tick,
)
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
from backend.core.wallet_reconciliation import WalletReconciler

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # --- Startup ---
    from datetime import datetime as _dt, timezone as _tz

    app.state.start_time = _dt.now(_tz.utc)
    logger.info("=" * 60)
    logger.info("BTC 5-MIN TRADING BOT v3.0")
    logger.info("=" * 60)
    logger.info("Initializing database...")

    init_db()

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

    logger.info("Starting wallet reconciliation recovery...")
    try:
        from backend.data.polymarket_clob import clob_from_settings
        
        db = SessionLocal()
        try:
            for mode in ["testnet", "live"]:
                if mode == "testnet" or settings.TRADING_MODE == "live":
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
                        logger.warning(f"Startup recovery [{mode}] failed: {e}", exc_info=True)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Wallet reconciliation startup failed: {e}", exc_info=True)

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

                    db = SessionLocal()
                    try:
                        state = db.query(BotState).first()
                        if state:
                            if settings.TRADING_MODE == "live":
                                state.bankroll = clob_balance
                            elif settings.TRADING_MODE == "testnet":
                                state.testnet_bankroll = clob_balance
                            db.commit()
                    finally:
                        db.close()
        except Exception as e:
            logger.warning(f"Failed to refresh balance cache: {e}")

    async def stats_broadcaster():
        from backend.api.ws_manager import stats_ws

        logger.info("Stats broadcaster task started")

        await refresh_balance_cache()

        BALANCE_REFRESH_INTERVAL = 30

        while True:
            try:
                if stats_ws.active_connections:
                    logger.debug(
                        f"Broadcasting stats to {len(stats_ws.active_connections)} clients"
                    )

                    now = time.time()
                    if now - _balance_cache["timestamp"] > BALANCE_REFRESH_INTERVAL:
                        await refresh_balance_cache()

                    db = SessionLocal()
                    try:
                        stats = await get_stats(db, None)
                        await stats_ws.broadcast(
                            {
                                "type": "stats_update",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data": stats.model_dump(),
                            }
                        )
                    finally:
                        db.close()
            except Exception as e:
                logger.error(f"Stats broadcaster error: {e}", exc_info=True)
            await asyncio.sleep(1)

    logger.info("Creating stats broadcaster background task...")
    stats_task = asyncio.create_task(stats_broadcaster())
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
                    asyncio.create_task(
                        orderbook_cache.update(
                            snapshot.asset_id, snapshot.bids, snapshot.asks
                        )
                    )
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

                market_ws_task = asyncio.create_task(market_ws.connect())
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

                                asyncio.create_task(refresh_balance_cache())
                        except Exception as e:
                            logger.error(
                                f"Error updating trade status: {e}", exc_info=True
                            )
                        finally:
                            db.close()

                    user_ws.on_user_order(handle_user_order)
                    user_ws.on_user_trade(handle_user_trade)

                    user_ws_task = asyncio.create_task(user_ws.connect())
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
        logger.error(f"Failed to start Polymarket WebSocket: {e}", exc_info=True)

    yield

    logger.info("Shutting down Polymarket WebSocket...")
    if market_ws_task:
        await shutdown_market_websocket()
        market_ws_task.cancel()
        try:
            await market_ws_task
        except asyncio.CancelledError:
            pass
        logger.info("Polymarket WebSocket shut down")

    if user_ws_task:
        await shutdown_user_websocket()
        user_ws_task.cancel()
        try:
            await user_ws_task
        except asyncio.CancelledError:
            pass
        logger.info("Polymarket User WebSocket shut down")

    logger.info("Cancelling stats broadcaster task...")
    stats_task.cancel()
    try:
        await stats_task
    except asyncio.CancelledError:
        logger.info("Stats broadcaster task cancelled")
        pass

    # --- Shutdown ---
    from backend.core.scheduler import stop_scheduler, scheduler as _scheduler

    logger.info("Shutdown initiated — stopping scheduler...")
    app.state.shutting_down = True

    # Stop APScheduler gracefully (sets running=False immediately, cancels worker task)
    stop_scheduler()

    # Give in-flight strategy jobs a grace period to complete before closing DB.
    # scheduler.shutdown(wait=False) cancels the scheduler but doesn't await running
    # coroutines. A 3-second grace period covers the typical strategy cycle duration.
    await asyncio.sleep(3.0)

    # Close database connections
    try:
        from backend.models.database import engine

        engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.exception(
            f"[api.main.lifespan] {type(e).__name__}: Error closing database connections: {str(e)}"
        )

    logger.info("Shutdown complete")


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

app.add_middleware(RateLimiterMiddleware, requests_per_minute=100)

# Include routers
app.include_router(auth_router)
app.include_router(markets_router)
app.include_router(trading_router)
app.include_router(copy_trading_router)
app.include_router(arbitrage_router)
app.include_router(market_intel_router)
app.include_router(auto_trader_router)
app.include_router(system_router)
app.include_router(backtest_router)
app.include_router(wallets_router)
app.include_router(analytics_router)


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
                    f"[api.main.ConnectionManager.broadcast] {type(e).__name__}: Failed to broadcast message to WebSocket connection: {str(e)}"
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


# Core endpoints
@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "BTC 5-Min Trading Bot API v3.0",
        "simulation_mode": settings.SIMULATION_MODE,
    }


@app.get("/api/health")
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
        logger.warning("Failed to get strategy health: %s", e)
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
    else:
        checks["redis"] = {"status": "not_configured", "fallback": "sqlite"}

    # 3. Polymarket CLOB connectivity
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

    # 4. Strategy heartbeats
    try:
        from backend.core.heartbeat import get_strategy_health

        healths = get_strategy_health(db)
        all_healthy = all(h["healthy"] or h["lag_seconds"] is None for h in healths)
        if not all_healthy and overall_status == "ok":
            overall_status = "degraded"
    except Exception as e:
        healths = []
        logger.warning("Failed to get strategy health: %s", e)
        if overall_status == "ok":
            overall_status = "degraded"

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


@app.get("/api/dashboard", response_model=DashboardData)
async def get_dashboard(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Get all dashboard data in one call - returns stats for all 3 modes."""
    stats = await get_stats(db, _, mode=None)

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
                change_24h=micro.momentum_15m * 96,  # rough extrapolation
                change_7d=0,
                market_cap=0,
                volume_24h=0,
                last_updated=datetime.now(timezone.utc),
            )
    except Exception as e:
        logger.warning(
            f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch BTC microstructure data, falling back to CoinGecko: {str(e)}"
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
                f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch BTC price from CoinGecko: {str(e)}"
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
            f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch active BTC markets: {str(e)}"
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
            f"[api.main.get_dashboard] {type(e).__name__}: Failed to scan for trading signals: {str(e)}"
        )

    # Recent trades (with TradeContext enrichment)
    trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(50).all()
    trade_ids = [t.id for t in trades]
    contexts = {}
    if trade_ids:
        for ctx in (
            db.query(TradeContext).filter(TradeContext.trade_id.in_(trade_ids)).all()
        ):
            contexts[ctx.trade_id] = ctx
    recent_trades = [
        TradeResponse(
            id=t.id,
            market_ticker=t.market_ticker,
            platform=t.platform,
            event_slug=t.event_slug,
            direction=t.direction,
            entry_price=t.entry_price,
            size=t.size,
            timestamp=t.timestamp,
            settled=t.settled,
            result=t.result,
            pnl=t.pnl,
            strategy=(contexts[t.id].strategy if t.id in contexts else None)
            or getattr(t, "strategy", None),
            signal_source=(contexts[t.id].signal_source if t.id in contexts else None)
            or getattr(t, "signal_source", None),
            confidence=(contexts[t.id].confidence if t.id in contexts else None)
            or getattr(t, "confidence", None),
        )
        for t in trades
    ]

    # Equity curve: track equity at each settled trade
    equity_trades = (
        db.query(Trade).filter(Trade.settled.is_(True)).order_by(Trade.timestamp).all()
    )
    equity_curve = []
    cumulative_pnl = 0
    for trade in equity_trades:
        if trade.pnl is not None:
            cumulative_pnl += trade.pnl
            equity_curve.append(
                {
                    "timestamp": trade.timestamp.isoformat(),
                    "pnl": cumulative_pnl,
                    "bankroll": settings.INITIAL_BANKROLL + cumulative_pnl,
                }
            )

    # Append current point with open positions reflected
    bot_state = db.query(BotState).first()
    if bot_state and equity_curve:
        if settings.TRADING_MODE == "paper":
            current_bankroll = (
                bot_state.paper_bankroll
                if bot_state.paper_bankroll is not None
                else settings.INITIAL_BANKROLL
            )
        elif settings.TRADING_MODE == "testnet":
            current_bankroll = (
                bot_state.testnet_bankroll
                if bot_state.testnet_bankroll is not None
                else settings.INITIAL_BANKROLL
            )
        else:
            current_bankroll = (
                bot_state.bankroll
                if bot_state.bankroll is not None
                else settings.INITIAL_BANKROLL
            )
        open_trades = db.query(Trade).filter(Trade.settled.is_(False)).all()
        unrealized = (
            sum((t.pnl or 0) for t in open_trades if t.pnl is not None)
            if open_trades
            else 0
        )
        last_point = equity_curve[-1].copy()
        last_point["timestamp"] = datetime.now(timezone.utc).isoformat()
        last_point["bankroll"] = current_bankroll + unrealized
        equity_curve.append(last_point)

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
            weather_signals_data = [_weather_signal_to_response(s) for s in wx_signals]

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
                f"[api.main.get_dashboard] {type(e).__name__}: Failed to fetch weather forecasts data: {str(e)}"
            )

    return DashboardData(
        stats=stats,
        btc_price=btc_price_data,
        microstructure=micro_data,
        windows=windows,
        active_signals=signals,
        recent_trades=recent_trades,
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


@app.get("/api/admin/sync-status", response_model=SyncStatusAllResponse)
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
        logger.error(f"Background sync failed for mode={mode}: {e}", exc_info=True)
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
    if mode not in ("testnet", "live"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'testnet' or 'live'"
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
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
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


@app.websocket("/ws/markets")
async def ws_markets(websocket: WebSocket, token: str = ""):
    """WebSocket endpoint for live market price updates."""
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await market_ws.connect(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        market_ws.disconnect(websocket)
    except Exception as e:
        logger.exception(
            f"[api.main.ws_markets] {type(e).__name__}: Market WebSocket error: {str(e)}"
        )
        market_ws.disconnect(websocket)


@app.websocket("/ws/whales")
async def ws_whales(websocket: WebSocket, token: str = ""):
    """WebSocket endpoint for whale trade notifications."""
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await whale_ws.connect(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        whale_ws.disconnect(websocket)
    except Exception as e:
        logger.exception(
            f"[api.main.ws_whales] {type(e).__name__}: Whale WebSocket error: {str(e)}"
        )
        whale_ws.disconnect(websocket)


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, token: str = ""):
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await ws_manager.connect(websocket)

    try:
        await websocket.send_json(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "success",
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
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.exception(
            f"[api.main.websocket_events] {type(e).__name__}: Events WebSocket error: {str(e)}"
        )
        ws_manager.disconnect(websocket)


@app.websocket("/ws/stats")
async def websocket_stats(websocket: WebSocket, token: str = ""):
    if settings.ADMIN_API_KEY and token != settings.ADMIN_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    from backend.api.ws_manager import stats_ws

    await stats_ws.connect(websocket)

    try:
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        logger.info("Stats WebSocket disconnected")
        stats_ws.disconnect(websocket)
    except Exception as e:
        logger.exception(f"Stats WebSocket error: {e}")
        stats_ws.disconnect(websocket)
    except Exception as e:
        logger.exception(f"Stats WebSocket error: {e}")
        stats_ws.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8100")))
