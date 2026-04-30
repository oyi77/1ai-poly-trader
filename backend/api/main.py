"""FastAPI backend for BTC 5-min trading bot dashboard."""

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Header,
    Request,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional, AsyncGenerator
import asyncio
from contextlib import asynccontextmanager
import os

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
from backend.api.agi_routes import router as agi_router
from backend.api.admin import router as admin_router
from backend.api.brain import router as brain_router
from backend.api.errors import router as errors_router
from backend.api.metrics_endpoint import router as metrics_router
from backend.api.alerts import router as alerts_router
from backend.core.wallet_reconciliation import WalletReconciler

# HFT shared data service
from backend.data.shared_service import router as shared_data_router
from backend.api.learning import router as learning_router

from backend.api.lifespan import lifespan
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
    
    from backend.api_websockets import brain_stream, activity_stream, proposals, livestream
    brain_stream.set_task_manager(app.state.task_manager)
    activity_stream.set_task_manager(app.state.task_manager)
    proposals.set_task_manager(app.state.task_manager)
    livestream.set_task_manager(app.state.task_manager)
    
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
app.include_router(admin_router, prefix="/api/v1")
# /api/bot/start alias for tests and older clients (canonical: /api/v1/bot/start)
app.include_router(system_router, prefix="/api")
app.include_router(brain_router, prefix="/api/v1")
app.include_router(errors_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(shared_data_router)
app.include_router(learning_router, prefix="/api/v1")
app.include_router(agi_router, prefix="/api/v1/agi")

from backend.api.dashboard import router as dashboard_router
app.include_router(dashboard_router, prefix="/api/v1")

from backend.api.sync import router as sync_router
app.include_router(sync_router, prefix="/api/v1")

from backend.api.websockets_routes import router as websockets_router
app.include_router(websockets_router)

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








if __name__ == "__main__":
    import uvicorn
    from backend.core.config_service import get_setting

    uvicorn.run(app, host="0.0.0.0", port=int(get_setting("PORT", default="8100")))
