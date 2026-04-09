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
from datetime import datetime
from typing import List, Optional, AsyncGenerator
import asyncio
import os
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
    logger.warning("eth_account not available - wallet creation disabled")
from backend.core.signals import scan_for_signals, TradingSignal
from backend.data.btc_markets import fetch_active_btc_markets
from backend.data.crypto import fetch_crypto_price, compute_btc_microstructure
from backend.core.errors import handle_errors
from backend.core.event_bus import event_bus, publish_event
from backend.api.ws_manager import market_ws, whale_ws, broadcast_market_tick, broadcast_whale_tick
from backend.api.auth import router as auth_router, require_admin
from backend.api.markets import router as markets_router
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

from pydantic import BaseModel
import logging

logger = logging.getLogger("trading_bot")

app = FastAPI(
    title="BTC 5-Min Trading Bot",
    description="Polymarket BTC Up/Down 5-minute market trading bot",
    version="3.0.0",
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
            except Exception:
                logger.exception("Failed to broadcast message to WebSocket connection")


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


# Startup / Shutdown
@app.on_event("startup")
async def startup():
    from datetime import datetime as _dt
    app.state.start_time = _dt.utcnow()
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
    logger.info(f"  - Strategies loaded: {', '.join(sorted(__import__('backend.strategies.registry', fromlist=['STRATEGY_REGISTRY']).STRATEGY_REGISTRY.keys()))}")

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


@app.on_event("shutdown")
async def shutdown():
    from backend.core.scheduler import stop_scheduler, scheduler as _scheduler

    logger.info("Shutdown initiated — stopping scheduler...")
    app.state.shutting_down = True

    # Stop APScheduler gracefully
    stop_scheduler()

    # Wait up to 30s for in-flight operations
    deadline = 30
    waited = 0
    while waited < deadline:
        if _scheduler is None or not getattr(_scheduler, "running", False):
            break
        await asyncio.sleep(0.5)
        waited += 0.5

    # Close database connections
    try:
        from backend.models.database import engine
        engine.dispose()
        logger.info("Database connections closed")
    except Exception:
        logger.exception("Error closing database connections")

    logger.info("Shutdown complete")


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
    """Return system health including per-strategy heartbeat status."""
    from backend.core.heartbeat import get_strategy_health

    healths = get_strategy_health(db)
    all_healthy = all(h["healthy"] or h["lag_seconds"] is None for h in healths)
    bot_state = db.query(BotState).first()
    return {
        "status": "ok" if all_healthy else "degraded",
        "strategies": healths,
        "timestamp": datetime.utcnow().isoformat(),
        "bot_running": bot_state.is_running if bot_state else False,
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
async def get_dashboard(db: Session = Depends(get_db)):
    """Get all dashboard data in one call."""
    stats = await get_stats(db)

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
                last_updated=datetime.utcnow(),
            )
    except Exception:
        logger.warning("Failed to fetch BTC microstructure data, falling back to CoinGecko")
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
        except Exception:
            logger.warning("Failed to fetch BTC price from CoinGecko")

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
    except Exception:
        logger.warning("Failed to fetch active BTC markets")

    # Signals — return ALL signals, mark which are actionable
    signals = []
    try:
        raw_signals = await scan_for_signals()
        signals = [
            _signal_to_response(s, actionable=s.passes_threshold) for s in raw_signals
        ]
    except Exception:
        logger.warning("Failed to scan for trading signals")

    # Recent trades (with TradeContext enrichment)
    trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(50).all()
    trade_ids = [t.id for t in trades]
    contexts = {}
    if trade_ids:
        for ctx in db.query(TradeContext).filter(TradeContext.trade_id.in_(trade_ids)).all():
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
            strategy=contexts[t.id].strategy if t.id in contexts else None,
            signal_source=contexts[t.id].signal_source if t.id in contexts else None,
            confidence=contexts[t.id].confidence if t.id in contexts else None,
        )
        for t in trades
    ]

    # Equity curve
    equity_trades = (
        db.query(Trade).filter(Trade.settled == True).order_by(Trade.timestamp).all()
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

    # Calibration summary
    calibration = _compute_calibration_summary(db)

    # Weather data (if enabled)
    weather_signals_data = []
    weather_forecasts_data = []
    if settings.WEATHER_ENABLED:
        try:
            from backend.core.weather_signals import scan_for_weather_signals
            from backend.data.weather import fetch_ensemble_forecast, CITY_CONFIG

            wx_signals = await scan_for_weather_signals()
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
        except Exception:
            logger.warning("Failed to fetch weather forecasts data")

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


@app.get("/api/events/stream")
async def events_stream(request: Request):
    """Server-Sent Events stream for real-time trade notifications."""
    from fastapi.responses import StreamingResponse
    import json as _json

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    event_bus.subscribe(queue)

    async def generate() -> AsyncGenerator[str, None]:
        # Send recent history on connect
        for event in event_bus.get_history():
            yield f"data: {_json.dumps(event)}\n\n"
        # Send connected heartbeat immediately
        yield f"data: {_json.dumps({'type': 'connected', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
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
async def ws_markets(websocket: WebSocket):
    """WebSocket endpoint for live market price updates."""
    await market_ws.connect(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        market_ws.disconnect(websocket)
    except Exception:
        logger.exception("Market WebSocket error")
        market_ws.disconnect(websocket)


@app.websocket("/ws/whales")
async def ws_whales(websocket: WebSocket):
    """WebSocket endpoint for whale trade notifications."""
    await whale_ws.connect(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        whale_ws.disconnect(websocket)
    except Exception:
        logger.exception("Whale WebSocket error")
        whale_ws.disconnect(websocket)


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await ws_manager.connect(websocket)

    try:
        await websocket.send_json(
            {
                "timestamp": datetime.utcnow().isoformat(),
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
                {"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()}
            )

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        logger.exception("Events WebSocket error")
        ws_manager.disconnect(websocket)



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8100")))
