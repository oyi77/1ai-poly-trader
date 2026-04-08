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
from backend.core.signals import scan_for_signals, TradingSignal
from backend.data.btc_markets import fetch_active_btc_markets
from backend.data.crypto import fetch_crypto_price, compute_btc_microstructure

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
                pass


ws_manager = ConnectionManager()


# Global SSE event broadcaster
_event_subscribers: list = []
_event_history: deque = deque(maxlen=50)


def _broadcast_event(event_type: str, data: dict):
    """Push an event to all connected SSE subscribers. Thread-safe via asyncio."""
    import json as _json

    payload = {
        "type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data,
    }
    _event_history.append(payload)
    for q in _event_subscribers[:]:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # subscriber is slow, drop event


def require_admin(authorization: Optional[str] = Header(None)):
    """Require admin API key if ADMIN_API_KEY is configured."""
    key = settings.ADMIN_API_KEY
    if not key:
        return  # No key configured = open (dev mode)
    if not authorization or authorization != f"Bearer {key}":
        raise HTTPException(
            status_code=401,
            detail="Unauthorized — set Authorization: Bearer <ADMIN_API_KEY>",
        )


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


class SignalResponse(BaseModel):
    market_ticker: str
    market_title: str
    platform: str
    direction: str
    model_probability: float
    market_probability: float
    edge: float
    confidence: float
    suggested_size: float
    reasoning: str
    timestamp: datetime
    category: str = "crypto"
    event_slug: Optional[str] = None
    btc_price: float = 0.0
    btc_change_24h: float = 0.0
    window_end: Optional[datetime] = None
    actionable: bool = False


class TradeResponse(BaseModel):
    id: int
    market_ticker: str
    platform: str
    event_slug: Optional[str] = None
    direction: str
    entry_price: float
    size: float
    timestamp: datetime
    settled: bool
    result: str
    pnl: Optional[float]
    strategy: Optional[str] = None
    signal_source: Optional[str] = None
    confidence: Optional[float] = None


class BotStats(BaseModel):
    bankroll: float
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl: float
    is_running: bool
    last_run: Optional[datetime]
    # Paper trading fields
    paper_pnl: float = 0.0
    paper_bankroll: float = 10000.0
    paper_trades: int = 0
    paper_wins: int = 0
    paper_win_rate: float = 0.0
    mode: str = "paper"
    pnl_source: str = "botstate"
    paper: dict = {}
    live: dict = {}


class CalibrationBucket(BaseModel):
    bucket: str
    predicted_avg: float
    actual_rate: float
    count: int


class CalibrationSummary(BaseModel):
    total_signals: int
    total_with_outcome: int
    accuracy: float
    avg_predicted_edge: float
    avg_actual_edge: float
    brier_score: float


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
    print("=" * 60)
    print("BTC 5-MIN TRADING BOT v3.0")
    print("=" * 60)
    print("Initializing database...")

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
            print(
                f"Created new bot state with ${settings.INITIAL_BANKROLL:,.2f} bankroll"
            )
        else:
            state.is_running = True
            db.commit()
            print(
                f"Loaded bot state: Bankroll ${state.bankroll:,.2f}, P&L ${state.total_pnl:+,.2f}, {state.total_trades} trades"
            )
    finally:
        db.close()

    print("")
    print("Configuration:")
    print(f"  - Simulation mode: {settings.SIMULATION_MODE}")
    print(f"  - Min edge threshold: {settings.MIN_EDGE_THRESHOLD:.0%}")
    print(f"  - Kelly fraction: {settings.KELLY_FRACTION:.0%}")
    print(f"  - Scan interval: {settings.SCAN_INTERVAL_SECONDS}s")
    print(f"  - Settlement interval: {settings.SETTLEMENT_INTERVAL_SECONDS}s")
    print("")

    # Load all strategies BEFORE starting scheduler
    from backend.strategies.registry import load_all_strategies
    print("Loading trading strategies...")
    load_all_strategies()
    print(f"  - Strategies loaded: {', '.join(sorted(__import__('backend.strategies.registry', fromlist=['STRATEGY_REGISTRY']).STRATEGY_REGISTRY.keys()))}")

    from backend.core.scheduler import start_scheduler, log_event

    start_scheduler()
    log_event("success", "BTC 5-min trading bot initialized")

    print("Bot is now running!")
    print(
        f"  - BTC scan: every {settings.SCAN_INTERVAL_SECONDS}s (edge >= {settings.MIN_EDGE_THRESHOLD:.0%})"
    )
    print(f"  - Settlement check: every {settings.SETTLEMENT_INTERVAL_SECONDS}s")
    if settings.WEATHER_ENABLED:
        print(
            f"  - Weather scan: every {settings.WEATHER_SCAN_INTERVAL_SECONDS}s (edge >= {settings.WEATHER_MIN_EDGE_THRESHOLD:.0%})"
        )
        print(f"  - Weather cities: {settings.WEATHER_CITIES}")
    else:
        print("  - Weather trading: DISABLED")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown():
    from backend.core.scheduler import stop_scheduler

    stop_scheduler()


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
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns all trading bot metrics in Prometheus text format.
    Scrape this endpoint with Prometheus or other monitoring systems.
    """
    from backend.monitoring import get_metrics
    return get_metrics()


@app.get("/api/stats", response_model=BotStats)
async def get_stats(db: Session = Depends(get_db)):
    state = db.query(BotState).first()
    if not state:
        raise HTTPException(status_code=404, detail="Bot state not initialized")

    win_rate = (
        state.winning_trades / state.total_trades if state.total_trades > 0 else 0
    )

    # Paper trading stats
    paper_pnl = state.paper_pnl or 0.0
    paper_bankroll = state.paper_bankroll or 10000.0
    paper_trades = state.paper_trades or 0
    paper_wins = state.paper_wins or 0
    paper_win_rate = paper_wins / paper_trades if paper_trades > 0 else 0.0

    # Fallback: if total_pnl is 0 but settled paper trades exist, recalculate from DB
    pnl_source = "botstate"
    if state.total_pnl == 0 and paper_trades > 0:
        db_paper_pnl = (
            db.query(func.sum(Trade.pnl)).filter(Trade.settled == True).scalar() or 0.0
        )
        if db_paper_pnl != 0:
            paper_pnl = db_paper_pnl
            pnl_source = "recalculated"

    return BotStats(
        bankroll=state.bankroll,
        total_trades=state.total_trades,
        winning_trades=state.winning_trades,
        win_rate=win_rate,
        total_pnl=state.total_pnl,
        is_running=state.is_running,
        last_run=state.last_run,
        paper_pnl=paper_pnl,
        paper_bankroll=paper_bankroll,
        paper_trades=paper_trades,
        paper_wins=paper_wins,
        paper_win_rate=paper_win_rate,
        mode=settings.TRADING_MODE,
        pnl_source=pnl_source,
        paper={
            "pnl": paper_pnl,
            "bankroll": paper_bankroll,
            "trades": paper_trades,
            "wins": paper_wins,
            "win_rate": paper_win_rate,
        },
        live={
            "pnl": state.total_pnl,
            "bankroll": state.bankroll,
            "trades": state.total_trades,
            "wins": state.winning_trades,
            "win_rate": win_rate,
        },
    )


# BTC-specific endpoints
@app.get("/api/btc/price", response_model=Optional[BtcPriceResponse])
async def get_btc_price():
    """Get current BTC price and momentum data."""
    try:
        btc = await fetch_crypto_price("BTC")
        if not btc:
            return None

        return BtcPriceResponse(
            price=btc.current_price,
            change_24h=btc.change_24h,
            change_7d=btc.change_7d,
            market_cap=btc.market_cap,
            volume_24h=btc.volume_24h,
            last_updated=btc.last_updated,
        )
    except Exception:
        return None


@app.get("/api/btc/windows", response_model=List[BtcWindowResponse])
async def get_btc_windows():
    """Get upcoming BTC 5-min windows with prices."""
    try:
        markets = await fetch_active_btc_markets()
        return [
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
        return []


@app.get("/api/signals", response_model=List[SignalResponse])
async def get_signals():
    """Get current BTC trading signals."""
    try:
        signals = await scan_for_signals()
        return [_signal_to_response(s) for s in signals]
    except Exception:
        return []


@app.get("/api/signals/history")
async def get_signals_history(
    limit: int = 100,
    offset: int = 0,
    market_type: Optional[str] = None,
    direction: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Return historical signals from the database with outcome data."""
    from backend.models.database import Signal as SignalModel

    query = db.query(SignalModel)
    if market_type:
        query = query.filter(SignalModel.market_type == market_type)
    if direction:
        query = query.filter(SignalModel.direction == direction)
    total = query.count()
    rows = (
        query.order_by(SignalModel.timestamp.desc()).offset(offset).limit(limit).all()
    )
    items = [
        {
            "id": r.id,
            "market_ticker": r.market_ticker,
            "platform": r.platform or "polymarket",
            "market_type": r.market_type or "btc",
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "direction": r.direction,
            "model_probability": r.model_probability,
            "market_probability": r.market_price,
            "edge": r.edge,
            "confidence": r.confidence,
            "suggested_size": r.suggested_size,
            "reasoning": r.reasoning,
            "executed": r.executed,
            "actual_outcome": r.actual_outcome,
            "outcome_correct": r.outcome_correct,
            "settlement_value": r.settlement_value,
            "settled_at": r.settled_at.isoformat() if r.settled_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@app.get("/api/signals/actionable", response_model=List[SignalResponse])
async def get_actionable_signals():
    """Get only signals that pass the edge threshold."""
    try:
        signals = await scan_for_signals()
        actionable = [s for s in signals if s.passes_threshold]
        return [_signal_to_response(s) for s in actionable]
    except Exception:
        return []


def _signal_to_response(s: TradingSignal, actionable: bool = False) -> SignalResponse:
    return SignalResponse(
        market_ticker=s.market.market_id,
        market_title=f"BTC 5m - {s.market.slug}",
        platform="polymarket",
        direction=s.direction,
        model_probability=s.model_probability,
        market_probability=s.market_probability,
        edge=s.edge,
        confidence=s.confidence,
        suggested_size=s.suggested_size,
        reasoning=s.reasoning,
        timestamp=s.timestamp,
        category="crypto",
        event_slug=s.market.slug,
        btc_price=s.btc_price,
        btc_change_24h=s.btc_change_24h,
        window_end=s.market.window_end,
        actionable=actionable,
    )


@app.get("/api/trades", response_model=List[TradeResponse])
async def get_trades(
    limit: int = 50, status: Optional[str] = None, db: Session = Depends(get_db)
):
    query = db.query(Trade)
    if status:
        query = query.filter(Trade.result == status)
    trades = query.order_by(Trade.timestamp.desc()).limit(limit).all()

    trade_ids = [t.id for t in trades]
    context_map = {}
    if trade_ids:
        contexts = (
            db.query(TradeContext).filter(TradeContext.trade_id.in_(trade_ids)).all()
        )
        context_map = {c.trade_id: c for c in contexts}

    result_list = []
    for t in trades:
        ctx = context_map.get(t.id)
        trade_dict = TradeResponse(
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
        )
        trade_dict = trade_dict.model_dump()
        trade_dict["strategy"] = (ctx.strategy if ctx else None) or getattr(
            t, "strategy", None
        )
        trade_dict["signal_source"] = (ctx.signal_source if ctx else None) or getattr(
            t, "signal_source", None
        )
        trade_dict["confidence"] = (ctx.confidence if ctx else None) or getattr(
            t, "confidence", None
        )
        result_list.append(trade_dict)

    return result_list


@app.get("/api/equity-curve")
async def get_equity_curve(db: Session = Depends(get_db)):
    trades = (
        db.query(Trade).filter(Trade.settled == True).order_by(Trade.timestamp).all()
    )

    curve = []
    cumulative_pnl = 0
    bankroll = settings.INITIAL_BANKROLL

    for trade in trades:
        if trade.pnl is not None:
            cumulative_pnl += trade.pnl
            curve.append(
                {
                    "timestamp": trade.timestamp.isoformat(),
                    "pnl": cumulative_pnl,
                    "bankroll": bankroll + cumulative_pnl,
                    "trade_id": trade.id,
                }
            )

    return curve


@app.post("/api/simulate-trade")
async def simulate_trade(signal_ticker: str, db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event

    signals = await scan_for_signals()
    signal = next((s for s in signals if s.market.market_id == signal_ticker), None)

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    state = db.query(BotState).first()
    if not state:
        raise HTTPException(status_code=500, detail="Bot state not initialized")

    entry_price = (
        signal.market.up_price if signal.direction == "up" else signal.market.down_price
    )

    trade = Trade(
        market_ticker=signal.market.market_id,
        platform="polymarket",
        event_slug=signal.market.slug,
        direction=signal.direction,
        entry_price=entry_price,
        size=min(signal.suggested_size, state.bankroll * 0.05),
        model_probability=signal.model_probability,
        market_price_at_entry=signal.market_probability,
        edge_at_entry=signal.edge,
    )

    db.add(trade)
    state.total_trades += 1
    db.commit()

    _broadcast_event(
        "trade_opened",
        {
            "trade_id": trade.id,
            "market_ticker": trade.market_ticker,
            "direction": trade.direction,
            "size": trade.size,
            "entry_price": trade.entry_price,
            "mode": settings.TRADING_MODE,
        },
    )

    log_event(
        "trade", f"Manual BTC trade: {signal.direction.upper()} {signal.market.slug}"
    )
    return {"status": "ok", "trade_id": trade.id, "size": trade.size}


@app.post("/api/run-scan")
async def run_scan(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    from backend.core.scheduler import run_manual_scan, log_event

    state = db.query(BotState).first()
    if state:
        state.last_run = datetime.utcnow()
        db.commit()

    log_event("info", "Manual scan triggered (BTC + Weather)")
    await run_manual_scan()

    signals = await scan_for_signals()
    actionable = [s for s in signals if s.passes_threshold]

    result = {
        "status": "ok",
        "total_signals": len(signals),
        "actionable_signals": len(actionable),
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Also run weather scan if enabled
    if settings.WEATHER_ENABLED:
        try:
            from backend.core.weather_signals import scan_for_weather_signals

            wx_signals = await scan_for_weather_signals()
            wx_actionable = [s for s in wx_signals if s.passes_threshold]
            result["weather_signals"] = len(wx_signals)
            result["weather_actionable"] = len(wx_actionable)
        except Exception:
            result["weather_signals"] = 0
            result["weather_actionable"] = 0

    return result


@app.post("/api/settle-trades")
async def settle_trades_endpoint(db: Session = Depends(get_db)):
    from backend.core.settlement import (
        settle_pending_trades,
        update_bot_state_with_settlements,
    )
    from backend.core.scheduler import log_event

    log_event("info", "Manual settlement triggered")

    settled = await settle_pending_trades(db)
    await update_bot_state_with_settlements(db, settled)

    return {
        "status": "ok",
        "settled_count": len(settled),
        "trades": [{"id": t.id, "result": t.result, "pnl": t.pnl} for t in settled],
    }


def _compute_calibration_summary(db: Session) -> Optional[CalibrationSummary]:
    """Compute calibration summary from settled signals."""
    total_signals = db.query(Signal).count()
    settled_signals = db.query(Signal).filter(Signal.outcome_correct.isnot(None)).all()

    if not settled_signals:
        if total_signals == 0:
            return None
        return CalibrationSummary(
            total_signals=total_signals,
            total_with_outcome=0,
            accuracy=0.0,
            avg_predicted_edge=0.0,
            avg_actual_edge=0.0,
            brier_score=0.0,
        )

    total_with_outcome = len(settled_signals)
    correct = sum(1 for s in settled_signals if s.outcome_correct)
    accuracy = correct / total_with_outcome if total_with_outcome > 0 else 0.0

    avg_predicted_edge = sum(abs(s.edge) for s in settled_signals) / total_with_outcome
    # Actual edge: for correct predictions, edge was real; for incorrect, edge was negative
    avg_actual_edge = (
        sum(abs(s.edge) if s.outcome_correct else -abs(s.edge) for s in settled_signals)
        / total_with_outcome
    )

    # Brier score: mean squared error of probability forecasts
    # For each signal: (predicted_prob - actual_outcome)^2
    brier_sum = 0.0
    for s in settled_signals:
        # Model probability is for UP; actual is 1.0 if UP won, 0.0 if DOWN won
        actual = s.settlement_value if s.settlement_value is not None else 0.5
        brier_sum += (s.model_probability - actual) ** 2
    brier_score = brier_sum / total_with_outcome

    return CalibrationSummary(
        total_signals=total_signals,
        total_with_outcome=total_with_outcome,
        accuracy=accuracy,
        avg_predicted_edge=avg_predicted_edge,
        avg_actual_edge=avg_actual_edge,
        brier_score=brier_score,
    )


@app.get("/api/calibration")
async def get_calibration(db: Session = Depends(get_db)):
    """Return calibration data: predicted probability vs actual win rate."""
    signals = db.query(Signal).filter(Signal.outcome_correct.isnot(None)).all()

    if not signals:
        return {"buckets": [], "summary": None}

    # Bucket signals by model_probability into 5% bins
    from collections import defaultdict

    buckets_data = defaultdict(lambda: {"predicted_sum": 0.0, "correct": 0, "total": 0})

    for s in signals:
        # Bin by 5% increments
        bin_start = int(s.model_probability * 100 // 5) * 5
        bin_end = bin_start + 5
        bucket_key = f"{bin_start}-{bin_end}%"

        buckets_data[bucket_key]["predicted_sum"] += s.model_probability
        buckets_data[bucket_key]["total"] += 1
        if s.outcome_correct:
            buckets_data[bucket_key]["correct"] += 1

    buckets = []
    for bucket_key in sorted(buckets_data.keys()):
        d = buckets_data[bucket_key]
        buckets.append(
            CalibrationBucket(
                bucket=bucket_key,
                predicted_avg=d["predicted_sum"] / d["total"],
                actual_rate=d["correct"] / d["total"],
                count=d["total"],
            )
        )

    summary = _compute_calibration_summary(db)

    return {"buckets": buckets, "summary": summary}


# Kalshi endpoints
@app.get("/api/kalshi/status")
async def get_kalshi_status():
    """Test Kalshi API authentication and return connection status."""
    from backend.data.kalshi_client import KalshiClient, kalshi_credentials_present

    if not kalshi_credentials_present():
        return {
            "connected": False,
            "error": "Kalshi credentials not configured (KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PATH)",
        }

    try:
        client = KalshiClient()
        balance_data = await client.get_balance()
        return {
            "connected": True,
            "balance": balance_data,
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
        }


# Weather endpoints
@app.get("/api/weather/forecasts", response_model=List[WeatherForecastResponse])
async def get_weather_forecasts():
    """Get ensemble forecasts for configured cities."""
    if not settings.WEATHER_ENABLED:
        return []

    try:
        from backend.data.weather import fetch_ensemble_forecast, CITY_CONFIG

        city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]
        forecasts = []

        for city_key in city_keys:
            if city_key not in CITY_CONFIG:
                continue
            forecast = await fetch_ensemble_forecast(city_key)
            if forecast:
                forecasts.append(
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

        return forecasts
    except Exception:
        return []


@app.get("/api/weather/markets", response_model=List[WeatherMarketResponse])
async def get_weather_markets():
    """Get active weather temperature markets."""
    if not settings.WEATHER_ENABLED:
        return []

    try:
        from backend.data.weather_markets import fetch_polymarket_weather_markets

        city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]
        markets = await fetch_polymarket_weather_markets(city_keys)

        # Also fetch Kalshi markets if enabled
        if settings.KALSHI_ENABLED:
            try:
                from backend.data.kalshi_client import kalshi_credentials_present
                from backend.data.kalshi_markets import fetch_kalshi_weather_markets

                if kalshi_credentials_present():
                    kalshi_markets = await fetch_kalshi_weather_markets(city_keys)
                    markets.extend(kalshi_markets)
            except Exception:
                pass

        return [
            WeatherMarketResponse(
                slug=m.slug,
                market_id=m.market_id,
                platform=m.platform,
                title=m.title,
                city_key=m.city_key,
                city_name=m.city_name,
                target_date=m.target_date.isoformat(),
                threshold_f=m.threshold_f,
                metric=m.metric,
                direction=m.direction,
                yes_price=m.yes_price,
                no_price=m.no_price,
                volume=m.volume,
            )
            for m in markets
        ]
    except Exception:
        return []


@app.get("/api/weather/signals", response_model=List[WeatherSignalResponse])
async def get_weather_signals():
    """Get current weather trading signals."""
    if not settings.WEATHER_ENABLED:
        return []

    try:
        from backend.core.weather_signals import scan_for_weather_signals

        signals = await scan_for_weather_signals()
        return [_weather_signal_to_response(s) for s in signals]
    except Exception:
        return []


def _weather_signal_to_response(s) -> WeatherSignalResponse:
    return WeatherSignalResponse(
        market_id=s.market.market_id,
        city_key=s.market.city_key,
        city_name=s.market.city_name,
        target_date=s.market.target_date.isoformat(),
        threshold_f=s.market.threshold_f,
        metric=s.market.metric,
        direction=s.direction,
        model_probability=s.model_probability,
        market_probability=s.market_probability,
        edge=s.edge,
        confidence=s.confidence,
        suggested_size=s.suggested_size,
        reasoning=s.reasoning,
        ensemble_mean=s.ensemble_mean,
        ensemble_std=s.ensemble_std,
        ensemble_members=s.ensemble_members,
        actionable=s.passes_threshold,
    )


@app.get("/api/polymarket/markets")
async def get_polymarket_markets(
    offset: int = 0,
    limit: int = 100,
    category: str | None = None
):
    """Get Polymarket CLOB markets with pagination."""
    try:
        from backend.core.market_scanner import fetch_all_active_markets

        markets = await fetch_all_active_markets(
            category=category,
            limit=limit + offset if limit else None
        )
        # Apply pagination
        paginated = markets[offset:offset + limit]
        return {
            "markets": [
                {
                    "ticker": m.ticker,
                    "slug": m.slug,
                    "question": m.question,
                    "category": m.category,
                    "yes_price": m.yes_price,
                    "no_price": m.no_price,
                    "volume": m.volume,
                    "liquidity": m.liquidity,
                    "end_date": m.end_date,
                }
                for m in paginated
            ],
            "total": len(markets),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"Failed to fetch Polymarket markets: {e}")
        return {"markets": [], "total": 0, "offset": offset, "limit": limit}


@app.get("/api/events", response_model=List[EventResponse])
async def get_events(limit: int = 50):
    from backend.core.scheduler import get_recent_events

    events = get_recent_events(limit)
    return [
        EventResponse(
            timestamp=e["timestamp"],
            type=e["type"],
            message=e["message"],
            data=e.get("data", {}),
        )
        for e in events
    ]


# Bot control
@app.post("/api/bot/start")
async def start_bot(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    from backend.core.scheduler import start_scheduler, log_event, is_scheduler_running

    state = db.query(BotState).first()
    if state and state.is_running:
        raise HTTPException(
            status_code=409, detail={"error": "already_running", "is_running": True}
        )

    if state:
        state.is_running = True
        db.commit()

    if not is_scheduler_running():
        start_scheduler()

    log_event("success", "Trading bot started")
    return {"status": "started", "is_running": True}


@app.post("/api/bot/stop")
async def stop_bot(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    from backend.core.scheduler import log_event

    state = db.query(BotState).first()
    if state and not state.is_running:
        raise HTTPException(
            status_code=409, detail={"error": "already_stopped", "is_running": False}
        )

    if state:
        state.is_running = False
        db.commit()

    log_event("info", "Trading bot paused")
    return {"status": "stopped", "is_running": False}


@app.post("/api/bot/reset")
async def reset_bot(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    from backend.core.scheduler import log_event

    try:
        trades_deleted = db.query(Trade).delete()
        state = db.query(BotState).first()
        if state:
            state.bankroll = settings.INITIAL_BANKROLL
            state.total_trades = 0
            state.winning_trades = 0
            state.total_pnl = 0.0
            state.is_running = True

        ai_logs_deleted = db.query(AILog).delete()
        db.commit()

        log_event(
            "success",
            f"Bot reset: {trades_deleted} trades deleted. Fresh start with ${settings.INITIAL_BANKROLL:,.2f}",
        )

        return {
            "status": "reset",
            "trades_deleted": trades_deleted,
            "ai_logs_deleted": ai_logs_deleted,
            "new_bankroll": settings.INITIAL_BANKROLL,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")


@app.post("/api/backtest/run")
async def run_backtest_frontend(
    body: FrontendBacktestRequest, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Run backtest against historical signals - matches frontend API contract."""
    from backend.core.backtesting import BacktestEngine, BacktestConfig
    from datetime import datetime, timedelta

    try:
        # Parse dates
        end_date = datetime.fromisoformat(body.end_date) if body.end_date else datetime.utcnow()
        start_date = datetime.fromisoformat(body.start_date) if body.start_date else end_date - timedelta(days=30)

        # Create config with defaults from settings
        config = BacktestConfig(
            initial_bankroll=body.initial_bankroll,
            max_trade_size=_DEFAULT_MAX_TRADE_SIZE,
            min_edge_threshold=_DEFAULT_MIN_EDGE_THRESHOLD,
            start_date=start_date,
            end_date=end_date,
            market_types=_DEFAULT_MARKET_TYPES,
            slippage_bps=DEFAULT_SLIPPAGE_BPS,
        )

        # Run backtest
        engine = BacktestEngine(config)
        result = engine.run(db)

        return {
            "strategy_name": body.strategy_name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "initial_bankroll": body.initial_bankroll,
            "results": {
                "summary": {
                    "total_signals": result.total_trades,
                    "total_trades": result.total_trades,
                    "winning_trades": result.winning_trades,
                    "losing_trades": result.losing_trades,
                    "win_rate": result.win_rate,
                    "initial_bankroll": body.initial_bankroll,
                    "final_equity": result.final_bankroll,
                    "total_pnl": result.total_pnl,
                    "total_return_pct": result.roi * 100,
                    "sharpe_ratio": result.sharpe_ratio,
                },
                "trade_log": [],
                "equity_curve": [],
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@app.post("/api/backtest")
async def run_backtest(
    body: BacktestRequest, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Run backtest against historical signals."""
    from backend.core.backtesting import BacktestEngine, BacktestConfig
    from datetime import datetime

    try:
        # Parse dates
        start_date = datetime.fromisoformat(body.start_date) if body.start_date else None
        end_date = datetime.fromisoformat(body.end_date) if body.end_date else None

        # Create config
        config = BacktestConfig(
            initial_bankroll=body.initial_bankroll,
            max_trade_size=body.max_trade_size,
            min_edge_threshold=body.min_edge_threshold,
            start_date=start_date,
            end_date=end_date,
            market_types=body.market_types,
            slippage_bps=body.slippage_bps,
        )

        # Run backtest
        engine = BacktestEngine(config)
        result = engine.run(db)

        return {
            "strategy_name": "signal_replay",
            "start_date": (start_date.isoformat() if start_date else body.start_date),
            "end_date": (end_date.isoformat() if end_date else body.end_date),
            "initial_bankroll": body.initial_bankroll,
            "results": {
                "summary": {
                    "total_signals": result.total_trades,
                    "total_trades": result.total_trades,
                    "winning_trades": result.winning_trades,
                    "losing_trades": result.losing_trades,
                    "win_rate": result.win_rate,
                    "initial_bankroll": body.initial_bankroll,
                    "final_equity": result.final_bankroll,
                    "total_pnl": result.total_pnl,
                    "total_return_pct": result.roi * 100,
                    "sharpe_ratio": result.sharpe_ratio,
                },
                "trade_log": [],
                "equity_curve": [],
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@app.get("/api/backtest/quick")
async def quick_backtest(
    days_back: int = 30,
    initial_bankroll: float = 1000.0,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Quick backtest for recent N days."""
    from backend.core.backtesting import run_quick_backtest

    try:
        result = run_quick_backtest(db, days_back=days_back, initial_bankroll=initial_bankroll)

        return {
            "status": "success",
            "result": {
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "total_pnl": result.total_pnl,
                "final_bankroll": result.final_bankroll,
                "win_rate": result.win_rate,
                "avg_win": result.avg_win,
                "avg_loss": result.avg_loss,
                "max_drawdown": result.max_drawdown,
                "sharpe_ratio": result.sharpe_ratio,
                "trades_per_day": result.trades_per_day,
                "roi": result.roi,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick backtest failed: {e}")

@app.get("/api/edge-performance")
async def get_edge_performance(
    track: str | None = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    """
    Returns aggregated performance metrics for edge discovery tracks.

    Metrics per track:
    - Total signals generated
    - Signals executed (paper)
    - Win rate (paper)
    - Total PNL (paper)
    - Sharpe ratio (paper)
    - Max drawdown (paper)
    """
    from datetime import datetime, timedelta
    from sqlalchemy import case, cast, Float

    # Calculate date threshold
    since_date = datetime.utcnow() - timedelta(days=days)

    # Build query
    query = db.query(
        Signal.track_name,
        func.count(Signal.id).label('total_signals'),
        func.sum(case((Signal.executed == True, 1))).label('signals_executed'),
        func.sum(case((Signal.outcome_correct == True, 1))).label('winning_trades'),
    ).filter(
        Signal.timestamp >= since_date,
        Signal.track_name.isnot(None),
    ).group_by(Signal.track_name)

    # Filter by specific track if requested
    if track:
        query = query.filter(Signal.track_name == track)

    results = query.all()

    # Calculate metrics for each track
    track_metrics = []
    for row in results:
        total_signals = row.total_signals or 0
        signals_executed = row.signals_executed or 0
        winning_trades = row.winning_trades or 0

        # Calculate win rate
        win_rate = (winning_trades / signals_executed) if signals_executed > 0 else 0.0

        # Get PNL data for this track
        pnl_query = db.query(
            func.sum(Trade.pnl).label('total_pnl'),
            func.count(Trade.id).label('trade_count'),
        ).join(
            Signal, Trade.signal_id == Signal.id
        ).filter(
            Signal.track_name == row.track_name,
            Signal.execution_mode == 'paper',
            Signal.timestamp >= since_date,
        )

        pnl_result = pnl_query.first()
        total_pnl = pnl_result.total_pnl or 0.0
        trade_count = pnl_result.trade_count or 0

        track_metrics.append({
            'track_name': row.track_name,
            'total_signals': total_signals,
            'signals_executed': signals_executed,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'trade_count': trade_count,
            'status': 'paper',  # All edge discovery starts in paper mode
        })

    return {
        'tracks': track_metrics,
        'days': days,
        'since_date': since_date.isoformat(),
    }


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
        pass
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
            pass

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
        pass

    # Signals — return ALL signals, mark which are actionable
    signals = []
    try:
        raw_signals = await scan_for_signals()
        signals = [
            _signal_to_response(s, actionable=s.passes_threshold) for s in raw_signals
        ]
    except Exception:
        pass

    # Recent trades
    trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(50).all()
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
            pass

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


@app.get("/api/copy/leaderboard", response_model=List[ScoredTraderResponse])
async def get_copy_leaderboard(limit: int = 50):
    """Return REAL top-scored traders scraped from Polymarket leaderboard.

    NO MOCK DATA - All metrics are real from polymarket.com!
    """
    try:
        from backend.data.polymarket_scraper import fetch_real_leaderboard

        # Fetch real leaderboard data from Polymarket website
        traders = await fetch_real_leaderboard(limit=limit)

        if not traders:
            logger.warning("No real leaderboard data available from Polymarket")
            return []

        # Convert to response format
        result = [
            ScoredTraderResponse(
                wallet=t["wallet"],
                pseudonym=t["pseudonym"],
                profit_30d=round(t["profit_30d"], 2),
                win_rate=round(t["win_rate"], 3),
                total_trades=t["total_trades"],
                unique_markets=t["unique_markets"],
                estimated_bankroll=round(t["estimated_bankroll"], 2),
                score=round(t["score"], 3),
                market_diversity=round(t["market_diversity"], 3),
            )
            for t in traders
        ]

        logger.info(f"Returning {len(result)} real traders from Polymarket leaderboard")
        return result

    except Exception as e:
        logger.error(f"Error fetching real leaderboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch real leaderboard: {str(e)}")


@app.get("/api/copy/signals", response_model=List[CopySignalResponse])
async def get_copy_signals(limit: int = 20):
    """Return recent copy trade signals from the DB."""
    try:
        db = SessionLocal()
        signals = (
            db.query(Signal)
            .filter(Signal.market_type == "copy")
            .order_by(Signal.timestamp.desc())
            .limit(limit)
            .all()
        )
        db.close()
        return [
            CopySignalResponse(
                source_wallet=s.sources[0] if s.sources else "",
                our_side=s.direction,
                our_outcome="YES",
                our_size=s.suggested_size,
                market_price=s.market_price,
                trader_score=s.confidence * 100,
                reasoning=s.reasoning,
                condition_id=s.market_ticker,
                title=s.market_ticker,
                timestamp=s.timestamp.isoformat(),
            )
            for s in signals
        ]
    except Exception:
        return []


# =========================================================================
# Admin endpoints
# =========================================================================


class SettingsUpdate(BaseModel):
    updates: dict


# Secret keywords for masking sensitive values
_SECRET_KEYWORDS = {"KEY", "SECRET", "PASSWORD", "PASSPHRASE", "TOKEN", "PRIVATE"}


def _is_secret(field_name: str) -> bool:
    upper = field_name.upper()
    return any(kw in upper for kw in _SECRET_KEYWORDS)


def _mask_value(field_name: str, value) -> str:
    if value is None or value == "" or value == "None":
        return ""
    if _is_secret(field_name):
        return "****"
    return value


def _persist_env_updates(updates: dict[str, str]) -> None:
    """
    Atomic .env file update helper.

    Reads existing .env, merges in updates, and writes back.
    Handles key=value parsing and preserves comments.

    Args:
        updates: dict of env var names to their new values
    """
    env_path = ".env"
    env_lines: dict[str, str] = {}

    # Read existing .env
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line_stripped = line.strip()
                if "=" in line_stripped and not line_stripped.startswith("#"):
                    k, v = line_stripped.split("=", 1)
                    env_lines[k.strip()] = v.strip()

    # Merge updates
    env_lines.update(updates)

    # Write back
    with open(env_path, "w") as f:
        for k, v in env_lines.items():
            f.write(f"{k}={v}\n")


def _get_grouped_settings() -> dict:
    """Return all settings grouped by category with secrets masked."""
    trading = {}
    weather = {}
    risk = {}
    indicators = {}
    ai = {}
    api_keys = {}
    telegram = {}
    security = {}
    system = {}

    field_groups = {
        "TRADING_MODE": trading,
        "INITIAL_BANKROLL": trading,
        "KELLY_FRACTION": trading,
        "MAX_TRADE_SIZE": trading,
        "DAILY_LOSS_LIMIT": trading,
        "MIN_EDGE_THRESHOLD": trading,
        "MAX_ENTRY_PRICE": trading,
        "MAX_TRADES_PER_WINDOW": trading,
        "MAX_TOTAL_PENDING_TRADES": trading,
        "BTC_PRICE_SOURCE": trading,
        "WEATHER_ENABLED": weather,
        "WEATHER_CITIES": weather,
        "WEATHER_MIN_EDGE_THRESHOLD": weather,
        "WEATHER_MAX_ENTRY_PRICE": weather,
        "WEATHER_MAX_TRADE_SIZE": weather,
        "WEATHER_SCAN_INTERVAL_SECONDS": weather,
        "WEATHER_SETTLEMENT_INTERVAL_SECONDS": weather,
        "MIN_TIME_REMAINING": risk,
        "MAX_TIME_REMAINING": risk,
        "MIN_MARKET_VOLUME": risk,
        "WEIGHT_RSI": indicators,
        "WEIGHT_MOMENTUM": indicators,
        "WEIGHT_VWAP": indicators,
        "WEIGHT_SMA": indicators,
        "WEIGHT_MARKET_SKEW": indicators,
        "GROQ_MODEL": ai,
        "AI_PROVIDER": ai,
        "AI_BASE_URL": ai,
        "AI_MODEL": ai,
        "AI_LOG_ALL_CALLS": ai,
        "AI_DAILY_BUDGET_USD": ai,
        "GROQ_API_KEY": api_keys,
        "AI_API_KEY": api_keys,
        "POLYMARKET_API_KEY": api_keys,
        "POLYMARKET_PRIVATE_KEY": api_keys,
        "POLYMARKET_API_SECRET": api_keys,
        "POLYMARKET_API_PASSPHRASE": api_keys,
        "KALSHI_API_KEY_ID": api_keys,
        "KALSHI_PRIVATE_KEY_PATH": api_keys,
        "TELEGRAM_BOT_TOKEN": telegram,
        "TELEGRAM_ADMIN_CHAT_IDS": telegram,
        "ADMIN_API_KEY": security,
        "CORS_ORIGINS": security,
        "DATABASE_URL": system,
        "SCAN_INTERVAL_SECONDS": system,
        "SETTLEMENT_INTERVAL_SECONDS": system,
        "KALSHI_ENABLED": system,
        "POLYGON_AMOY_RPC": system,
        "POLYGON_AMOY_CHAIN_ID": system,
        "POLYMARKET_TESTNET_CLOB_HOST": system,
    }

    for field_name, group in field_groups.items():
        if hasattr(settings, field_name):
            raw = getattr(settings, field_name)
            group[field_name] = _mask_value(field_name, raw)

    return {
        "trading": trading,
        "weather": weather,
        "risk": risk,
        "indicators": indicators,
        "ai": ai,
        "api_keys": api_keys,
        "telegram": telegram,
        "security": security,
        "system": system,
    }


class AdminLoginBody(BaseModel):
    password: str


@app.get("/api/admin/auth-required")
async def auth_required_endpoint():
    """Returns whether admin authentication is configured."""
    return {"auth_required": bool(settings.ADMIN_API_KEY)}


@app.post("/api/admin/login")
async def admin_login(body: AdminLoginBody):
    """Verify admin password. Returns success; client stores the password as bearer token."""
    if not settings.ADMIN_API_KEY:
        return {"success": True, "auth_required": False}
    if body.password != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"success": True, "auth_required": True}


class ChangePasswordBody(BaseModel):
    new_password: str


@app.post("/api/admin/change-password")
async def change_admin_password(
    body: ChangePasswordBody, _: None = Depends(require_admin)
):
    """Change the admin password (ADMIN_API_KEY). Persists to .env and hot-reloads."""
    new_pw = body.new_password.strip()
    if not new_pw:
        raise HTTPException(status_code=400, detail="Password cannot be empty")

    _persist_env_updates({"ADMIN_API_KEY": new_pw})
    settings.ADMIN_API_KEY = new_pw
    logger.info("Admin password changed")
    return {"status": "ok", "message": "Password updated — please re-login"}


@app.get("/api/admin/settings")
async def get_admin_settings(_: None = Depends(require_admin)):
    """Return all configurable settings grouped by category."""
    return _get_grouped_settings()


@app.post("/api/admin/settings")
async def update_admin_settings(body: SettingsUpdate, _: None = Depends(require_admin)):
    """Update settings at runtime and persist to .env file."""
    env_updates = {}

    for field, value in body.updates.items():
        if not hasattr(settings, field):
            continue
        # Skip if secret placeholder sent back
        if str(value) == "****":
            continue
        # Type coerce
        current = getattr(settings, field)
        if isinstance(current, bool):
            value = str(value).lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            value = int(value)
        elif isinstance(current, float):
            value = float(value)
        setattr(settings, field, value)
        # Strip characters that could corrupt .env format
        safe_value = str(value).replace("\n", "").replace("\r", "").replace("\x00", "")
        # For string fields that are comma-separated lists (cities, origins, etc.),
        # strip any trailing key=value injections (chars after unexpected = in list values)
        if isinstance(current, str) and "," in safe_value and "=" in safe_value:
            safe_value = safe_value.split("=")[0].rstrip()
        env_updates[field] = safe_value

    _persist_env_updates(env_updates)

    from backend.core.scheduler import reschedule_jobs

    scheduler_result = reschedule_jobs()

    return {
        "status": "ok",
        "message": f"Updated {len(env_updates)} settings",
        "scheduler": scheduler_result,
    }


class ModeSwitch(BaseModel):
    mode: str


class CredentialsUpdate(BaseModel):
    private_key: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    api_passphrase: str | None = None


@app.post("/api/admin/mode")
async def switch_mode(body: ModeSwitch, _: None = Depends(require_admin)):
    """Switch trading mode at runtime and persist to .env."""
    new_mode = body.mode.lower()
    if new_mode not in ("paper", "testnet", "live"):
        raise HTTPException(
            status_code=400, detail="mode must be paper, testnet, or live"
        )

    old_mode = settings.TRADING_MODE
    settings.TRADING_MODE = new_mode
    _persist_env_updates({"TRADING_MODE": new_mode})

    logger.info(f"Trading mode switched: {old_mode} → {new_mode}")
    return {"status": "ok", "mode": new_mode, "previous_mode": old_mode}


@app.post("/api/admin/credentials")
async def update_credentials(body: CredentialsUpdate, _: None = Depends(require_admin)):
    """Update Polymarket trading credentials, persist to .env, and hot-reload settings."""
    env_updates = {
        k: v.strip()
        for k, v in {
            "POLYMARKET_PRIVATE_KEY": body.private_key,
            "POLYMARKET_API_KEY": body.api_key,
            "POLYMARKET_API_SECRET": body.api_secret,
            "POLYMARKET_API_PASSPHRASE": body.api_passphrase,
        }.items()
        if v and v.strip()
    }

    _persist_env_updates(env_updates)

    # Hot-reload into running settings object
    if body.private_key and body.private_key.strip():
        settings.POLYMARKET_PRIVATE_KEY = body.private_key.strip()
    if body.api_key and body.api_key.strip():
        settings.POLYMARKET_API_KEY = body.api_key.strip()
    if body.api_secret and body.api_secret.strip():
        settings.POLYMARKET_API_SECRET = body.api_secret.strip()
    if body.api_passphrase and body.api_passphrase.strip():
        settings.POLYMARKET_API_PASSPHRASE = body.api_passphrase.strip()

    has_private_key = bool(settings.POLYMARKET_PRIVATE_KEY)
    has_api_key = bool(settings.POLYMARKET_API_KEY)
    has_api_secret = bool(settings.POLYMARKET_API_SECRET)
    has_api_passphrase = bool(settings.POLYMARKET_API_PASSPHRASE)

    logger.info(f"Credentials updated: {list(env_updates.keys())}")

    # Restart polyedge-bot to pick up new credentials
    import subprocess as _subprocess

    try:
        _subprocess.run(
            ["pm2", "restart", "polyedge-bot"],
            capture_output=True,
            timeout=10,
        )
        logger.info("polyedge-bot restarted to apply new credentials")
    except Exception as _e:
        logger.warning(f"Could not restart polyedge-bot: {_e}")

    return {
        "status": "ok",
        "updated": list(env_updates.keys()),
        "restarted_bot": True,
        "creds_paper": True,
        "creds_testnet": has_private_key,
        "creds_live": has_private_key
        and has_api_key
        and has_api_secret
        and has_api_passphrase,
        "missing_for_testnet": [] if has_private_key else ["POLYMARKET_PRIVATE_KEY"],
        "missing_for_live": [
            k
            for k, v in {
                "POLYMARKET_PRIVATE_KEY": has_private_key,
                "POLYMARKET_API_KEY": has_api_key,
                "POLYMARKET_API_SECRET": has_api_secret,
                "POLYMARKET_API_PASSPHRASE": has_api_passphrase,
            }.items()
            if not v
        ],
    }


@app.get("/api/admin/system")
async def get_admin_system(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Return system health overview."""
    state = db.query(BotState).first()
    pending_trades = db.query(Trade).filter(Trade.settled == False).count()
    db_trade_count = db.query(Trade).count()
    db_signal_count = db.query(Signal).count()

    uptime = (datetime.utcnow() - app.state.start_time if hasattr(app.state, 'start_time') else datetime.utcnow()).total_seconds()

    has_private_key = bool(settings.POLYMARKET_PRIVATE_KEY)
    has_api_key = bool(settings.POLYMARKET_API_KEY)
    has_api_secret = bool(settings.POLYMARKET_API_SECRET)
    has_api_passphrase = bool(settings.POLYMARKET_API_PASSPHRASE)

    return {
        "trading_mode": settings.TRADING_MODE,
        "bot_running": state.is_running if state else False,
        "uptime_seconds": int(uptime),
        "pending_trades": pending_trades,
        "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "kalshi_enabled": settings.KALSHI_ENABLED,
        "weather_enabled": settings.WEATHER_ENABLED,
        "db_trade_count": db_trade_count,
        "db_signal_count": db_signal_count,
        # Credential readiness per mode
        "creds_paper": True,  # paper needs no credentials
        "creds_testnet": has_private_key,
        "creds_live": has_private_key
        and has_api_key
        and has_api_secret
        and has_api_passphrase,
        "missing_for_testnet": [] if has_private_key else ["POLYMARKET_PRIVATE_KEY"],
        "missing_for_live": [
            k
            for k, v in {
                "POLYMARKET_PRIVATE_KEY": has_private_key,
                "POLYMARKET_API_KEY": has_api_key,
                "POLYMARKET_API_SECRET": has_api_secret,
                "POLYMARKET_API_PASSPHRASE": has_api_passphrase,
            }.items()
            if not v
        ],
    }


@app.post("/api/admin/alerts/test")
async def test_alert(_: None = Depends(require_admin)):
    """Send a test Telegram alert to verify bot configuration."""
    from backend.core.heartbeat import _send_telegram_alert_sync

    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN not configured")
    _send_telegram_alert_sync("✅ PolyEdge alert test — bot is configured correctly")
    return {"status": "ok", "message": "Test alert sent"}


# =========================================================================
# Strategy Config CRUD
# =========================================================================


@app.get("/api/strategies")
async def list_strategies_endpoint(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """List all registered strategies merged with their DB config."""
    from backend.strategies.registry import (
        load_all_strategies,
        STRATEGY_REGISTRY,
        list_strategies as _list_strategies,
    )

    load_all_strategies()

    metas = {m.name: m for m in _list_strategies()}
    configs = {c.strategy_name: c for c in db.query(StrategyConfig).all()}

    result = []
    for name, meta in metas.items():
        cfg = configs.get(name)
        import json as _json

        result.append(
            {
                "name": name,
                "description": meta.description,
                "category": meta.category,
                "default_params": meta.default_params,
                "enabled": cfg.enabled if cfg else False,
                "interval_seconds": cfg.interval_seconds if cfg else 60,
                "params": _json.loads(cfg.params)
                if cfg and cfg.params
                else meta.default_params,
                "updated_at": cfg.updated_at.isoformat()
                if cfg and cfg.updated_at
                else None,
            }
        )
    return result


@app.get("/api/strategies/{name}")
async def get_strategy(
    name: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Get a single strategy by name."""
    from backend.strategies.registry import STRATEGY_REGISTRY, load_all_strategies

    load_all_strategies()
    if name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not registered")
    cfg = db.query(StrategyConfig).filter(StrategyConfig.strategy_name == name).first()
    import json as _json
    from backend.strategies.registry import list_strategies as _ls

    meta = next((m for m in _ls() if m.name == name), None)
    return {
        "name": name,
        "description": meta.description if meta else "",
        "category": meta.category if meta else "",
        "enabled": cfg.enabled if cfg else False,
        "interval_seconds": cfg.interval_seconds if cfg else 60,
        "params": _json.loads(cfg.params)
        if cfg and cfg.params
        else (meta.default_params if meta else {}),
        "updated_at": cfg.updated_at.isoformat() if cfg and cfg.updated_at else None,
    }


class StrategyUpdate(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None
    params: dict | None = None


@app.put("/api/strategies/{name}")
async def update_strategy(
    name: str,
    body: StrategyUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Upsert strategy config and hot-reload scheduler."""
    from backend.strategies.registry import STRATEGY_REGISTRY, load_all_strategies

    load_all_strategies()
    if name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not registered")

    cfg = db.query(StrategyConfig).filter(StrategyConfig.strategy_name == name).first()
    if not cfg:
        cfg = StrategyConfig(strategy_name=name, enabled=False, interval_seconds=60)
        db.add(cfg)

    import json as _json

    if body.enabled is not None:
        cfg.enabled = body.enabled
    if body.interval_seconds is not None:
        cfg.interval_seconds = body.interval_seconds
    if body.params is not None:
        cfg.params = _json.dumps(body.params)

    db.commit()
    db.refresh(cfg)

    # Hot-reload scheduler
    from backend.core.scheduler import schedule_strategy, unschedule_strategy

    if cfg.enabled:
        schedule_strategy(name, cfg.interval_seconds or 60)
    else:
        unschedule_strategy(name)

    return {
        "status": "ok",
        "name": name,
        "enabled": cfg.enabled,
        "interval_seconds": cfg.interval_seconds,
    }


@app.post("/api/strategies/{name}/run-now")
async def run_strategy_now(
    name: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Execute one strategy cycle synchronously and return the result."""
    from backend.strategies.registry import STRATEGY_REGISTRY, load_all_strategies
    from backend.strategies.base import StrategyContext

    load_all_strategies()

    strategy_cls = STRATEGY_REGISTRY.get(name)
    if not strategy_cls:
        raise HTTPException(
            status_code=404, detail=f"Strategy '{name}' not in registry"
        )

    cfg = db.query(StrategyConfig).filter(StrategyConfig.strategy_name == name).first()
    import json as _json

    params = {}
    if cfg and cfg.params:
        try:
            params = _json.loads(cfg.params)
        except Exception:
            pass

    ctx = StrategyContext(
        db=db,
        clob=None,
        settings=settings,
        logger=logger,
        params=params,
        mode=settings.TRADING_MODE,
    )
    strategy = strategy_cls()
    result = await strategy.run(ctx)

    return {
        "name": name,
        "decisions_recorded": result.decisions_recorded,
        "trades_attempted": result.trades_attempted,
        "trades_placed": result.trades_placed,
        "errors": result.errors,
        "cycle_duration_ms": result.cycle_duration_ms,
    }


class MarketWatchCreate(BaseModel):
    ticker: str
    category: str | None = None
    source: str | None = None
    config: dict | None = None
    enabled: bool = True


class MarketWatchUpdate(BaseModel):
    category: str | None = None
    source: str | None = None
    config: dict | None = None
    enabled: bool | None = None


class WalletConfigCreate(BaseModel):
    address: str
    pseudonym: str | None = None
    source: str = "user"
    tags: list[str] | None = None
    enabled: bool = True
    notes: str | None = None


class WalletConfigUpdate(BaseModel):
    pseudonym: str | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    notes: str | None = None


# =========================================================================
# MarketWatch CRUD
# =========================================================================


@app.get("/api/markets/watch")
async def list_market_watches(
    enabled: bool | None = None,
    category: str | None = None,
    source: str | None = None,
    q: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    query = db.query(MarketWatch)
    if enabled is not None:
        query = query.filter(MarketWatch.enabled == enabled)
    if category:
        query = query.filter(MarketWatch.category == category)
    if source:
        query = query.filter(MarketWatch.source == source)
    if q:
        query = query.filter(MarketWatch.ticker.contains(q))
    total = query.count()
    col = getattr(MarketWatch, sort, MarketWatch.created_at)
    if order == "desc":
        col = col.desc()
    items = query.order_by(col).offset(offset).limit(limit).all()
    return {
        "items": [
            {
                "id": m.id,
                "ticker": m.ticker,
                "category": m.category,
                "source": m.source,
                "enabled": m.enabled,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in items
        ],
        "total": total,
    }


@app.post("/api/markets/watch", status_code=201)
async def create_market_watch(
    body: MarketWatchCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    existing = db.query(MarketWatch).filter(MarketWatch.ticker == body.ticker).first()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Market '{body.ticker}' already watched"
        )
    import json as _json

    row = MarketWatch(
        ticker=body.ticker,
        category=body.category,
        source=body.source,
        config=_json.dumps(body.config) if body.config else None,
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "ticker": row.ticker, "enabled": row.enabled}


@app.put("/api/markets/watch/{watch_id}")
async def update_market_watch(
    watch_id: int,
    body: MarketWatchUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    row = db.query(MarketWatch).filter(MarketWatch.id == watch_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="MarketWatch not found")
    import json as _json

    if body.category is not None:
        row.category = body.category
    if body.source is not None:
        row.source = body.source
    if body.config is not None:
        row.config = _json.dumps(body.config)
    if body.enabled is not None:
        row.enabled = body.enabled
    db.commit()
    return {"id": row.id, "ticker": row.ticker, "enabled": row.enabled}


@app.delete("/api/markets/watch/{watch_id}", status_code=204)
async def delete_market_watch(
    watch_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    row = db.query(MarketWatch).filter(MarketWatch.id == watch_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="MarketWatch not found")
    db.delete(row)
    db.commit()


# =========================================================================
# WalletConfig CRUD + Leaderboard
# =========================================================================


@app.get("/api/wallets/config")
async def list_wallet_configs(
    enabled: bool | None = None,
    source: str | None = None,
    q: str | None = None,
    sort: str = "added_at",
    order: str = "desc",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    query = db.query(WalletConfig)
    if enabled is not None:
        query = query.filter(WalletConfig.enabled == enabled)
    if source:
        query = query.filter(WalletConfig.source == source)
    if q:
        query = query.filter(
            (WalletConfig.address.contains(q)) | (WalletConfig.pseudonym.contains(q))
        )
    total = query.count()
    col = getattr(WalletConfig, sort, WalletConfig.added_at)
    if order == "desc":
        col = col.desc()
    items = query.order_by(col).offset(offset).limit(limit).all()
    import json as _json

    return {
        "items": [
            {
                "id": w.id,
                "address": w.address,
                "pseudonym": w.pseudonym,
                "source": w.source,
                "tags": _json.loads(w.tags) if w.tags else [],
                "enabled": w.enabled,
                "notes": w.notes,
                "added_at": w.added_at.isoformat() if w.added_at else None,
            }
            for w in items
        ],
        "total": total,
    }


@app.post("/api/wallets/config", status_code=201)
async def create_wallet_config(
    body: WalletConfigCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    existing = (
        db.query(WalletConfig).filter(WalletConfig.address == body.address).first()
    )
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Wallet '{body.address}' already configured"
        )
    import json as _json

    row = WalletConfig(
        address=body.address,
        pseudonym=body.pseudonym,
        source=body.source,
        tags=_json.dumps(body.tags) if body.tags else None,
        enabled=body.enabled,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "address": row.address, "enabled": row.enabled}


@app.put("/api/wallets/config/{wallet_id}")
async def update_wallet_config(
    wallet_id: int,
    body: WalletConfigUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    row = db.query(WalletConfig).filter(WalletConfig.id == wallet_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="WalletConfig not found")
    import json as _json

    if body.pseudonym is not None:
        row.pseudonym = body.pseudonym
    if body.tags is not None:
        row.tags = _json.dumps(body.tags)
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.notes is not None:
        row.notes = body.notes
    db.commit()
    return {"id": row.id, "address": row.address, "enabled": row.enabled}


@app.delete("/api/wallets/config/{wallet_id}", status_code=204)
async def delete_wallet_config(
    wallet_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    row = db.query(WalletConfig).filter(WalletConfig.id == wallet_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="WalletConfig not found")
    db.delete(row)
    db.commit()


@app.get("/api/wallets/leaderboard")
async def get_wallet_leaderboard(
    min_pnl: float | None = None,
    min_winrate: float | None = None,
    source: str | None = None,
    q: str | None = None,
    sort: str = "added_at",
    order: str = "desc",
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Return WalletConfig rows merged with any available leaderboard data."""
    query = db.query(WalletConfig).filter(WalletConfig.enabled == True)
    if source:
        query = query.filter(WalletConfig.source == source)
    if q:
        query = query.filter(
            (WalletConfig.address.contains(q)) | (WalletConfig.pseudonym.contains(q))
        )
    total = query.count()
    col = getattr(WalletConfig, sort, WalletConfig.added_at)
    if order == "desc":
        col = col.desc()
    items = query.order_by(col).offset(offset).limit(limit).all()
    import json as _json

    return {
        "items": [
            {
                "address": w.address,
                "pseudonym": w.pseudonym or w.address[:8] + "...",
                "source": w.source,
                "tags": _json.loads(w.tags) if w.tags else [],
                "enabled": w.enabled,
                "added_at": w.added_at.isoformat() if w.added_at else None,
            }
            for w in items
        ],
        "total": total,
    }


# =========================================================================
# Decision Log
# =========================================================================


@app.get("/api/decisions")
async def list_decisions(
    strategy: str | None = None,
    decision: str | None = None,
    market: str | None = None,
    since: str | None = None,
    until: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List decision log entries with filtering."""
    query = db.query(DecisionLog)
    if strategy:
        query = query.filter(DecisionLog.strategy == strategy)
    if decision:
        query = query.filter(DecisionLog.decision == decision.upper())
    if market:
        query = query.filter(DecisionLog.market_ticker.contains(market))
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            query = query.filter(DecisionLog.created_at >= since_dt)
        except ValueError:
            pass
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            query = query.filter(DecisionLog.created_at <= until_dt)
        except ValueError:
            pass
    total = query.count()
    col = getattr(DecisionLog, sort, DecisionLog.created_at)
    if order == "desc":
        col = col.desc()
    items = query.order_by(col).offset(offset).limit(limit).all()
    return {
        "items": [
            {
                "id": d.id,
                "strategy": d.strategy,
                "market_ticker": d.market_ticker,
                "decision": d.decision,
                "confidence": d.confidence,
                "reason": d.reason,
                "outcome": d.outcome,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in items
        ],
        "total": total,
    }


@app.get("/api/decisions/export")
async def export_decisions(
    format: str = "jsonl",
    strategy: str | None = None,
    decision: str | None = None,
    limit: int = 10000,
    db: Session = Depends(get_db),
):
    """Export decision log as JSONL for ML training."""
    from fastapi.responses import StreamingResponse
    import json as _json
    import io

    query = db.query(DecisionLog)
    if strategy:
        query = query.filter(DecisionLog.strategy == strategy)
    if decision:
        query = query.filter(DecisionLog.decision == decision.upper())
    items = query.order_by(DecisionLog.created_at.desc()).limit(limit).all()

    def generate():
        for d in items:
            signal_data = None
            if d.signal_data:
                try:
                    signal_data = _json.loads(d.signal_data)
                except Exception:
                    signal_data = d.signal_data
            row = {
                "id": d.id,
                "strategy": d.strategy,
                "market_ticker": d.market_ticker,
                "decision": d.decision,
                "confidence": d.confidence,
                "signal_data": signal_data,
                "reason": d.reason,
                "outcome": d.outcome,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            yield _json.dumps(row) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=decisions.jsonl"},
    )


@app.get("/api/decisions/{decision_id}")
async def get_decision(decision_id: int, db: Session = Depends(get_db)):
    """Get a single decision log entry including full signal_data."""
    row = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    import json as _json

    signal_data = None
    if row.signal_data:
        try:
            signal_data = _json.loads(row.signal_data)
        except Exception:
            signal_data = row.signal_data
    return {
        "id": row.id,
        "strategy": row.strategy,
        "market_ticker": row.market_ticker,
        "decision": row.decision,
        "confidence": row.confidence,
        "signal_data": signal_data,
        "reason": row.reason,
        "outcome": row.outcome,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.get("/api/admin/ai/suggest")
async def ai_suggest_params(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Use AI to analyze recent performance and suggest parameter improvements."""
    from backend.ai.optimizer import ParameterOptimizer

    optimizer = ParameterOptimizer(settings)
    return await optimizer.get_suggestions(db)


@app.get("/api/admin/scheduler/jobs")
async def get_scheduler_jobs_endpoint(_: None = Depends(require_admin)):
    """Return current APScheduler job list."""
    from backend.core.scheduler import get_scheduler_jobs

    return get_scheduler_jobs()


@app.get("/api/copy-trader/status")
async def get_copy_trader_status():
    """Return copy trader status with tracked wallets."""
    wallet_details = []
    recent_signals = []
    errors = []

    try:
        from backend.strategies.copy_trader import LeaderboardScorer
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as http:
            scorer = LeaderboardScorer(http)
            traders = await scorer.fetch_and_score(top_n=10)

        wallet_details = [
            {
                "address": t.wallet[:10] + "..." if len(t.wallet) > 10 else t.wallet,
                "pseudonym": t.pseudonym,
                "score": t.score,
                "profit_30d": t.profit_30d,
            }
            for t in traders
        ]
    except Exception as e:
        errors.append({"source": "leaderboard_scorer", "message": str(e)})

    try:
        db = SessionLocal()
        copy_signals = (
            db.query(Signal)
            .filter(Signal.market_type == "copy")
            .order_by(Signal.timestamp.desc())
            .limit(10)
            .all()
        )
        recent_signals = [
            {
                "market_ticker": s.market_ticker,
                "direction": s.direction,
                "size": s.suggested_size,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in copy_signals
        ]
        db.close()
    except Exception as e:
        errors.append({"source": "db_signals", "message": str(e)})

    has_any_data = bool(wallet_details or recent_signals)
    if not errors:
        status = "ok"
    elif has_any_data:
        status = "degraded"
    else:
        status = "down"

    response_body = {
        "status": status,
        "errors": errors,
        "last_scan_at": datetime.utcnow().isoformat(),
        "enabled": True,
        "tracked_wallets": len(wallet_details),
        "wallet_details": wallet_details,
        "recent_signals": recent_signals,
    }

    if status == "down":
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=response_body)

    return response_body


@app.get("/api/copy-trader/positions")
async def get_copy_trader_positions(db: Session = Depends(get_db)):
    """Return recent copy trader position entries from DB."""
    from backend.models.database import CopyTraderEntry

    entries = (
        db.query(CopyTraderEntry)
        .order_by(CopyTraderEntry.opened_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "wallet": e.wallet,
            "condition_id": e.condition_id,
            "side": e.side,
            "size": e.size,
            "opened_at": e.opened_at.isoformat() if e.opened_at else None,
        }
        for e in entries
    ]


@app.get("/api/settlements")
async def get_settlements(
    limit: int = 100, offset: int = 0, db: Session = Depends(get_db)
):
    from backend.models.database import SettlementEvent

    events = (
        db.query(SettlementEvent)
        .order_by(SettlementEvent.settled_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "trade_id": e.trade_id,
            "market_ticker": e.market_ticker,
            "resolved_outcome": e.resolved_outcome,
            "pnl": e.pnl,
            "settled_at": e.settled_at.isoformat() if e.settled_at else None,
            "source": e.source,
        }
        for e in events
    ]


@app.get("/api/events/stream")
async def events_stream(request: Request):
    """Server-Sent Events stream for real-time trade notifications."""
    from fastapi.responses import StreamingResponse
    import json as _json

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_subscribers.append(queue)

    async def generate() -> AsyncGenerator[str, None]:
        # Send recent history on connect
        for event in list(_event_history):
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
            if queue in _event_subscribers:
                _event_subscribers.remove(queue)

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
        ws_manager.disconnect(websocket)


# ============================================================================
# Phase 2 endpoints — whales, arbitrage, news, predictions, auto-trader
# ============================================================================

@app.get("/api/whales/transactions")
async def get_whale_transactions(limit: int = 50):
    from backend.models.database import WhaleTransaction
    db = SessionLocal()
    try:
        rows = db.query(WhaleTransaction).order_by(WhaleTransaction.observed_at.desc()).limit(min(limit, 500)).all()
        return [
            {
                "id": r.id, "tx_hash": r.tx_hash, "wallet": r.wallet,
                "market_id": r.market_id, "side": r.side, "size_usd": r.size_usd,
                "block_number": r.block_number,
                "observed_at": r.observed_at.isoformat() if r.observed_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


# In-memory cache for arbitrage scans (60s TTL)
_arb_cache: dict = {"timestamp": 0.0, "data": []}


@app.get("/api/arbitrage/opportunities")
async def get_arbitrage_opportunities():
    """Live arbitrage scan over recent Polymarket Gamma markets, cached 60s."""
    import time as _time
    from backend.core.arbitrage_detector import ArbitrageDetector
    from backend.core.market_scanner import fetch_all_active_markets

    now = _time.time()
    if now - _arb_cache["timestamp"] < 60 and _arb_cache["data"]:
        return {"opportunities": _arb_cache["data"], "cached": True}

    try:
        markets = await fetch_all_active_markets(limit=200)
        detector = ArbitrageDetector()
        market_dicts = [
            {
                "market_id": m.ticker or m.slug,
                "yes_price": m.yes_price,
                "no_price": m.no_price,
                "question": m.question,
            }
            for m in markets
        ]
        ops = detector.scan_all(market_dicts)[:25]
        data = [op.__dict__ for op in ops]
        _arb_cache["timestamp"] = now
        _arb_cache["data"] = data
        return {"opportunities": data, "cached": False, "scanned": len(market_dicts)}
    except Exception as e:
        logger.warning(f"arbitrage scan failed: {e}")
        return {"opportunities": [], "error": str(e)}


@app.get("/api/news/feed")
async def get_news_feed():
    try:
        from backend.data.feed_aggregator import FeedAggregator
        agg = FeedAggregator()
        items = await agg.fetch_all()
        return [
            {
                "source": i.source, "title": i.title, "link": i.link,
                "published_at": i.published_at.isoformat() if i.published_at else None,
                "summary": i.summary,
            }
            for i in items[:100]
        ]
    except Exception as e:
        return {"error": str(e), "items": []}


@app.get("/api/predictions/{market_id}")
async def get_prediction(market_id: str):
    from backend.ai.prediction_engine import PredictionEngine
    engine = PredictionEngine()
    # Stub features — PE-013 will wire real market data
    features = engine.extract_features({"volume": 0}, {})
    pred = engine.predict(features)
    return {"market_id": market_id, "prediction": pred.__dict__}


@app.get("/api/auto-trader/pending")
async def list_pending_approvals(_admin=Depends(require_admin)):
    from backend.models.database import PendingApproval
    db = SessionLocal()
    try:
        rows = (
            db.query(PendingApproval)
            .filter(PendingApproval.status == "pending")
            .order_by(PendingApproval.created_at.desc())
            .limit(100)
            .all()
        )
        return [
            {
                "id": r.id,
                "market_id": r.market_id,
                "direction": r.direction,
                "size": r.size,
                "confidence": r.confidence,
                "signal_data": r.signal_data,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.post("/api/auto-trader/approve/{trade_id}")
async def approve_pending_trade(trade_id: int, _admin=Depends(require_admin)):
    from backend.models.database import PendingApproval
    db = SessionLocal()
    try:
        row = db.query(PendingApproval).filter(PendingApproval.id == trade_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        row.status = "approved"
        from datetime import datetime as _dt
        row.decided_at = _dt.utcnow()
        db.commit()
        return {"id": row.id, "status": row.status}
    finally:
        db.close()


@app.post("/api/auto-trader/reject/{trade_id}")
async def reject_pending_trade(trade_id: int, _admin=Depends(require_admin)):
    from backend.models.database import PendingApproval
    from datetime import datetime as _dt
    db = SessionLocal()
    try:
        row = db.query(PendingApproval).filter(PendingApproval.id == trade_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        row.status = "rejected"
        row.decided_at = _dt.utcnow()
        db.commit()
        return {"id": row.id, "status": row.status}
    finally:
        db.close()


# WebSocket channels for live market + whale streams
_ws_market_clients: list = []
_ws_whale_clients: list = []


@app.websocket("/ws/markets")
async def ws_markets(websocket: WebSocket):
    await websocket.accept()
    _ws_market_clients.append(websocket)
    try:
        await websocket.send_json({"type": "connected", "channel": "markets"})
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _ws_market_clients:
            _ws_market_clients.remove(websocket)


@app.websocket("/ws/whales")
async def ws_whales(websocket: WebSocket):
    await websocket.accept()
    _ws_whale_clients.append(websocket)
    try:
        await websocket.send_json({"type": "connected", "channel": "whales"})
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _ws_whale_clients:
            _ws_whale_clients.remove(websocket)


async def broadcast_market_tick(payload: dict) -> None:
    dead = []
    for ws in list(_ws_market_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in _ws_market_clients:
            _ws_market_clients.remove(d)


async def broadcast_whale_tick(payload: dict) -> None:
    dead = []
    for ws in list(_ws_whale_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in _ws_whale_clients:
            _ws_whale_clients.remove(d)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
