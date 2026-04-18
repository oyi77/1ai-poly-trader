"""System routes - stats, bot control, backtest, events."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
import json as _json
import asyncio

from backend.config import settings
from backend.models.database import (
    get_db,
    BotState,
    Trade,
    AILog,
    DecisionLog,
    StrategyConfig,
)
from backend.api.auth import require_admin
from backend.core.signals import scan_for_signals
import logging

logger = logging.getLogger("trading_bot")

router = APIRouter(tags=["system"])

_ticker_price_cache = {}
_ticker_price_cache_timestamps = {}
_CACHE_TTL_SECONDS = 60


# ============================================================================
# Pydantic Response Models
# ============================================================================


class SyncMetadata(BaseModel):
    """Metadata about database synchronization state."""
    last_synced_at: Optional[datetime] = None
    orphaned_count: int = 0
    external_imports_count: int = 0


class BotStats(BaseModel):
    bankroll: float
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl: float
    is_running: bool
    last_run: Optional[datetime]
    initial_bankroll: float = 10000.0
    paper_pnl: float = 0.0
    paper_bankroll: float = 10000.0
    paper_trades: int = 0
    paper_wins: int = 0
    paper_win_rate: float = 0.0
    testnet_pnl: float = 0.0
    testnet_bankroll: float = 100.0
    testnet_trades: int = 0
    testnet_wins: int = 0
    testnet_win_rate: float = 0.0
    mode: str = "paper"
    pnl_source: str = "botstate"
    paper: dict = {}
    testnet: dict = {}
    live: dict = {}
    active_mode: str = "paper"
    open_exposure: float = 0.0
    open_trades: int = 0
    settled_trades: int = 0
    settled_wins: int = 0
    unrealized_pnl: float = 0.0
    position_cost: float = 0.0
    position_market_value: float = 0.0
    sync_metadata: Optional[SyncMetadata] = None


class EventResponse(BaseModel):
    timestamp: str
    type: str
    message: str
    data: dict = {}


# ============================================================================
# Stats Endpoint
# ============================================================================


@router.get("/api/stats", response_model=BotStats)
async def get_stats(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    mode: Optional[str] = Query(None)
):
    # Query all 3 mode states
    paper_state = db.query(BotState).filter_by(mode="paper").first()
    testnet_state = db.query(BotState).filter_by(mode="testnet").first()
    live_state = db.query(BotState).filter_by(mode="live").first()
    
    # Use provided mode or current mode as primary
    effective_mode = mode or settings.TRADING_MODE
    if effective_mode == "paper":
        state = paper_state
    elif effective_mode == "testnet":
        state = testnet_state
    else:
        state = live_state
    
    if not state:
        raise HTTPException(status_code=404, detail="Bot state not initialized")

    paper_pnl = (paper_state.total_pnl or 0.0) if paper_state else 0.0
    paper_bankroll = (
        paper_state.bankroll
        if paper_state and paper_state.bankroll is not None
        else settings.INITIAL_BANKROLL
    )
    paper_trades = (paper_state.total_trades or 0) if paper_state else 0
    paper_wins = (paper_state.winning_trades or 0) if paper_state else 0
    paper_win_rate = paper_wins / paper_trades if paper_trades > 0 else 0.0

    sync_metadata = None
    
    if effective_mode in ("testnet", "live"):
        live_trades = (
            db.query(func.count(Trade.id))
            .filter(Trade.trading_mode == effective_mode, Trade.settled)
            .scalar()
            or 0
        )
        live_wins = (
            db.query(func.count(Trade.id))
            .filter(
                Trade.trading_mode == effective_mode,
                Trade.settled,
                Trade.pnl > 0,
            )
            .scalar()
            or 0
        )
        live_pnl = (
            db.query(func.sum(Trade.pnl))
            .filter(Trade.trading_mode == effective_mode, Trade.settled)
            .scalar()
            or 0.0
        )
        
        orphaned_count = (
            db.query(func.count(Trade.id))
            .filter(Trade.trading_mode == effective_mode, Trade.result == "orphaned")
            .scalar()
            or 0
        )
        external_imports_count = (
            db.query(func.count(Trade.id))
            .filter(Trade.trading_mode == effective_mode, Trade.source == "external")
            .scalar()
            or 0
        )
        
        sync_metadata = SyncMetadata(
            last_synced_at=live_state.last_sync_at if live_state else None,
            orphaned_count=orphaned_count,
            external_imports_count=external_imports_count,
        )
        
        if live_state and live_pnl != (live_state.total_pnl or 0.0):
            logger.warning(
                f"Stat change detected for {effective_mode}: DB PnL={live_pnl} vs BotState={live_state.total_pnl}. "
                f"Orphaned={orphaned_count}, External={external_imports_count}"
            )
        
        live_bankroll = (
            state.bankroll if state.bankroll is not None else settings.INITIAL_BANKROLL
        )
        live_win_rate = live_wins / live_trades if live_trades > 0 else 0.0
    else:
        live_pnl = (live_state.total_pnl or 0.0) if live_state else 0.0
        live_bankroll = (
            live_state.bankroll if live_state and live_state.bankroll is not None else settings.INITIAL_BANKROLL
        )
        live_trades = (live_state.total_trades or 0) if live_state else 0
        live_wins = (live_state.winning_trades or 0) if live_state else 0
        live_win_rate = live_wins / live_trades if live_trades > 0 else 0.0

    testnet_pnl = (testnet_state.total_pnl or 0.0) if testnet_state else 0.0
    testnet_bankroll = (
        testnet_state.bankroll if testnet_state and testnet_state.bankroll is not None else 100.0
    )
    testnet_trades = (testnet_state.total_trades or 0) if testnet_state else 0
    testnet_wins = (testnet_state.winning_trades or 0) if testnet_state else 0
    testnet_win_rate = testnet_wins / testnet_trades if testnet_trades > 0 else 0.0

    # Calculate per-mode unrealized PnL for all 3 modes
    async def calculate_mode_unrealized_pnl(mode: str):
        """Calculate unrealized PnL for a specific mode."""
        mode_trades = (
            db.query(Trade)
            .filter(~Trade.settled, Trade.trading_mode == mode)
            .all()
        )
        
        open_trades_count = len(mode_trades)
        open_exposure_amount = sum((t.size or 0.0) for t in mode_trades)
        
        unrealized_pnl = 0.0
        position_cost = 0.0
        position_market_value = 0.0
        
        if mode_trades:
            try:
                import httpx
                import time as _time

                tickers = list({t.market_ticker for t in mode_trades if t.market_ticker})
                if tickers:
                    ticker_to_price = {}
                    now = _time.time()

                    async def fetch_ticker_price(ticker):
                        if ticker in _ticker_price_cache:
                            cache_time = _ticker_price_cache_timestamps.get(ticker, 0)
                            if now - cache_time < _CACHE_TTL_SECONDS:
                                return ticker, _ticker_price_cache[ticker]

                        try:
                            async with httpx.AsyncClient(timeout=5.0) as client:
                                r = await client.get(
                                    f"https://gamma-api.polymarket.com/markets?slug={ticker}",
                                    timeout=5.0,
                                )
                                data = r.json()
                                if data and isinstance(data, list) and len(data) > 0:
                                    m = data[0]
                                    price_data = {
                                        "yes_price": float(m.get("yes_price", 0.5)),
                                        "no_price": float(m.get("no_price", 0.5)),
                                    }
                                    _ticker_price_cache[ticker] = price_data
                                    _ticker_price_cache_timestamps[ticker] = now
                                    return ticker, price_data
                        except Exception as e:
                            logger.warning(f"Failed to fetch price for {ticker}: {e}")
                        return ticker, None

                    tasks = [fetch_ticker_price(ticker) for ticker in tickers[:20]]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if not isinstance(result, Exception) and result:
                            ticker, price = result
                            if price:
                                ticker_to_price[ticker] = price

                    for t in mode_trades:
                        size = t.size or 0.0
                        position_cost += size
                        if not t.market_ticker or t.market_ticker not in ticker_to_price:
                            continue
                        prices = ticker_to_price[t.market_ticker]
                        entry = t.entry_price or 0.5
                        direction = t.direction
                        if direction == "up":
                            current_price = prices["yes_price"]
                        else:
                            current_price = prices["no_price"]
                        if entry > 0 and entry < 1:
                            shares = size / entry
                            if direction == "up":
                                mkt_val = shares * current_price
                            else:
                                mkt_val = shares * (1 - current_price)
                        else:
                            mkt_val = size
                        position_market_value += mkt_val
                    unrealized_pnl = round(position_market_value - position_cost, 2)
                    position_cost = round(position_cost, 2)
                    position_market_value = round(position_market_value, 2)
            except Exception:
                unrealized_pnl = 0.0
        
        return {
            "open_trades": open_trades_count,
            "open_exposure": open_exposure_amount,
            "unrealized_pnl": unrealized_pnl,
            "position_cost": position_cost,
            "position_market_value": position_market_value,
        }
    
    # Calculate unrealized PnL for all 3 modes in parallel
    paper_unrealized, testnet_unrealized, live_unrealized = await asyncio.gather(
        calculate_mode_unrealized_pnl("paper"),
        calculate_mode_unrealized_pnl("testnet"),
        calculate_mode_unrealized_pnl("live"),
    )
    
    # Use effective_mode's values for top-level fields (backward compatibility)
    if effective_mode == "paper":
        mode_unrealized = paper_unrealized
    elif effective_mode == "testnet":
        mode_unrealized = testnet_unrealized
    else:
        mode_unrealized = live_unrealized
    
    open_trades_count = mode_unrealized["open_trades"]
    open_exposure_amount = mode_unrealized["open_exposure"]
    unrealized_pnl = mode_unrealized["unrealized_pnl"]
    position_cost = mode_unrealized["position_cost"]
    position_market_value = mode_unrealized["position_market_value"]
    
    # Query settled trades for effective_mode
    settled_trades_count = (
        db.query(func.count(Trade.id))
        .filter(Trade.settled, Trade.trading_mode == effective_mode)
        .scalar()
        or 0
    )
    settled_wins_count = (
        db.query(func.count(Trade.id))
        .filter(Trade.settled, Trade.trading_mode == effective_mode, Trade.pnl > 0)
        .scalar()
        or 0
    )

    pnl_source = "botstate"
    if effective_mode == "paper" and paper_pnl == 0 and paper_trades > 0:
        db_pnl = (
            db.query(func.sum(Trade.pnl))
            .filter(Trade.settled.is_(True), Trade.trading_mode == "paper")
            .scalar()
            or 0.0
        )
        if db_pnl != 0:
            paper_pnl = db_pnl
            pnl_source = "recalculated"
    elif effective_mode == "testnet" and testnet_pnl == 0 and testnet_trades > 0:
        db_pnl = (
            db.query(func.sum(Trade.pnl))
            .filter(Trade.settled.is_(True), Trade.trading_mode == "testnet")
            .scalar()
            or 0.0
        )
        if db_pnl != 0:
            testnet_pnl = db_pnl
            pnl_source = "recalculated"
    elif effective_mode == "live" and live_pnl == 0 and live_trades > 0:
        db_pnl = (
            db.query(func.sum(Trade.pnl))
            .filter(Trade.settled.is_(True), Trade.trading_mode == "live")
            .scalar()
            or 0.0
        )
        if db_pnl != 0:
            live_pnl = db_pnl
            pnl_source = "recalculated"

    if effective_mode == "paper":
        display_bankroll = paper_bankroll
        display_trades = paper_trades
        display_wins = paper_wins
        display_win_rate = paper_win_rate
        display_pnl = paper_pnl
    elif effective_mode == "testnet":
        display_bankroll = testnet_bankroll
        display_trades = testnet_trades
        display_wins = testnet_wins
        display_win_rate = testnet_win_rate
        display_pnl = testnet_pnl
    else:
        display_bankroll = live_bankroll
        display_trades = live_trades
        display_wins = live_wins
        display_win_rate = live_win_rate
        display_pnl = live_pnl

    return BotStats(
        bankroll=display_bankroll,
        total_trades=display_trades,
        winning_trades=display_wins,
        win_rate=display_win_rate,
        total_pnl=display_pnl,
        is_running=state.is_running,
        last_run=state.last_run,
        initial_bankroll=settings.INITIAL_BANKROLL,
        paper_pnl=paper_pnl,
        paper_bankroll=paper_bankroll,
        paper_trades=paper_trades,
        paper_wins=paper_wins,
        paper_win_rate=paper_win_rate,
        testnet_pnl=testnet_pnl,
        testnet_bankroll=testnet_bankroll,
        testnet_trades=testnet_trades,
        testnet_wins=testnet_wins,
        testnet_win_rate=testnet_win_rate,
        mode=effective_mode,
        pnl_source=pnl_source,
        paper={
            "pnl": paper_pnl,
            "bankroll": paper_bankroll,
            "trades": paper_trades,
            "wins": paper_wins,
            "win_rate": paper_win_rate,
            "open_trades": paper_unrealized["open_trades"],
            "open_exposure": paper_unrealized["open_exposure"],
            "unrealized_pnl": paper_unrealized["unrealized_pnl"],
            "position_cost": paper_unrealized["position_cost"],
            "position_market_value": paper_unrealized["position_market_value"],
        },
        testnet={
            "pnl": testnet_pnl,
            "bankroll": testnet_bankroll,
            "trades": testnet_trades,
            "wins": testnet_wins,
            "win_rate": testnet_win_rate,
            "open_trades": testnet_unrealized["open_trades"],
            "open_exposure": testnet_unrealized["open_exposure"],
            "unrealized_pnl": testnet_unrealized["unrealized_pnl"],
            "position_cost": testnet_unrealized["position_cost"],
            "position_market_value": testnet_unrealized["position_market_value"],
        },
        live={
            "pnl": live_pnl,
            "bankroll": live_bankroll,
            "trades": live_trades,
            "wins": live_wins,
            "win_rate": live_win_rate,
            "open_trades": live_unrealized["open_trades"],
            "open_exposure": live_unrealized["open_exposure"],
            "unrealized_pnl": live_unrealized["unrealized_pnl"],
            "position_cost": live_unrealized["position_cost"],
            "position_market_value": live_unrealized["position_market_value"],
        },
        active_mode=settings.TRADING_MODE,
        open_exposure=open_exposure_amount,
        open_trades=open_trades_count,
        settled_trades=settled_trades_count,
        settled_wins=settled_wins_count,
        unrealized_pnl=unrealized_pnl,
        position_cost=position_cost,
        position_market_value=position_market_value,
        sync_metadata=sync_metadata,
    )


# ============================================================================
# AI Status & Control
# ============================================================================


@router.get("/api/stats/strategies")
async def get_strategy_stats(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Return P&L breakdown per strategy."""
    from sqlalchemy import case

    results = (
        db.query(
            Trade.strategy,
            func.count(Trade.id).label("total_trades"),
            func.sum(case((Trade.result == "win", 1), else_=0)).label("wins"),
            func.sum(case((Trade.result == "loss", 1), else_=0)).label("losses"),
            func.sum(case((Trade.settled, Trade.pnl), else_=0)).label(
                "total_pnl"
            ),
            func.avg(Trade.edge_at_entry).label("avg_edge"),
            func.avg(Trade.size).label("avg_size"),
        )
        .filter(Trade.strategy.isnot(None))
        .group_by(Trade.strategy)
        .all()
    )

    strategies = []
    for r in results:
        total = r.wins + r.losses
        strategies.append(
            {
                "strategy": r.strategy or "unknown",
                "total_trades": r.total_trades,
                "wins": r.wins,
                "losses": r.losses,
                "pending": r.total_trades - r.wins - r.losses,
                "win_rate": r.wins / total if total > 0 else 0,
                "total_pnl": round(r.total_pnl or 0, 2),
                "avg_edge": round(r.avg_edge or 0, 4),
                "avg_size": round(r.avg_size or 0, 2),
            }
        )

    return {
        "strategies": sorted(strategies, key=lambda s: s["total_pnl"], reverse=True)
    }


@router.get("/api/ai/status")
async def get_ai_status(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Return AI system status: enabled, provider, budget usage."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    spent_today = (
        db.query(func.coalesce(func.sum(AILog.cost_usd), 0.0))
        .filter(AILog.timestamp >= today_start)
        .scalar()
        or 0.0
    )
    calls_today = (
        db.query(func.count(AILog.id)).filter(AILog.timestamp >= today_start).scalar()
        or 0
    )

    return {
        "enabled": settings.AI_ENABLED,
        "provider": settings.AI_PROVIDER,
        "model": settings.AI_MODEL or settings.GROQ_MODEL,
        "daily_budget": settings.AI_DAILY_BUDGET_USD,
        "spent_today": round(spent_today, 4),
        "remaining": round(max(0, settings.AI_DAILY_BUDGET_USD - spent_today), 4),
        "calls_today": calls_today,
        "signal_weight": settings.AI_SIGNAL_WEIGHT,
    }


@router.post("/api/ai/toggle")
async def toggle_ai(_: None = Depends(require_admin)):
    """Toggle AI-enhanced signals on/off."""
    settings.AI_ENABLED = not settings.AI_ENABLED
    logger.info("AI signals %s", "ENABLED" if settings.AI_ENABLED else "DISABLED")
    return {"enabled": settings.AI_ENABLED}


# ============================================================================
# Bot Control Endpoints
# ============================================================================


@router.post("/api/bot/start")
async def start_bot(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    from backend.core.scheduler import start_scheduler, log_event, is_scheduler_running

    mode = settings.TRADING_MODE
    state = db.query(BotState).filter_by(mode=mode).first()
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


@router.post("/api/bot/stop")
async def stop_bot(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    from backend.core.scheduler import log_event

    mode = settings.TRADING_MODE
    state = db.query(BotState).filter_by(mode=mode).first()
    if state and not state.is_running:
        raise HTTPException(
            status_code=409, detail={"error": "already_stopped", "is_running": False}
        )

    if state:
        state.is_running = False
        db.commit()

    log_event("info", "Trading bot paused")
    return {"status": "stopped", "is_running": False}


class ResetRequest(BaseModel):
    confirm: bool = False


@router.post("/api/bot/reset")
async def reset_bot(
    body: ResetRequest, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to confirm reset. This deletes ALL trades and resets bankroll.",
        )
    from backend.core.scheduler import log_event

    try:
        trades_deleted = db.query(Trade).delete()
        
        for mode in ["paper", "testnet", "live"]:
            state = db.query(BotState).filter_by(mode=mode).first()
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


# ============================================================================
# Backtest Endpoints
# ============================================================================


class BacktestRequest(BaseModel):
    initial_bankroll: float = 1000.0
    max_trade_size: float = 100.0
    min_edge_threshold: float = 0.02
    start_date: str | None = None  # ISO format datetime
    end_date: str | None = None  # ISO format datetime
    market_types: list[str] = ["BTC", "Weather", "CopyTrader"]
    slippage_bps: int = 5  # basis points


@router.post("/api/backtest")
async def run_backtest(
    body: BacktestRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Run backtest against historical signals."""
    from backend.core.backtesting import BacktestEngine, BacktestConfig

    try:
        # Parse dates
        start_date = (
            datetime.fromisoformat(body.start_date) if body.start_date else None
        )
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
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(
            status_code=500, detail="Backtest failed — check server logs"
        )


@router.get("/api/backtest/quick")
async def quick_backtest(
    days_back: int = 30,
    initial_bankroll: float = 1000.0,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Quick backtest for recent N days."""
    from backend.core.backtesting import run_quick_backtest

    try:
        result = run_quick_backtest(
            db, days_back=days_back, initial_bankroll=initial_bankroll
        )

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
        logger.error(f"Quick backtest failed: {e}")
        raise HTTPException(
            status_code=500, detail="Quick backtest failed — check server logs"
        )


# ============================================================================
# Events Endpoints
# ============================================================================


@router.get("/api/events", response_model=List[EventResponse])
async def get_events(limit: int = 50, _: None = Depends(require_admin)):
    from backend.core.scheduler import get_recent_events

    limit = min(limit, 500)
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


@router.post("/api/run-scan")
async def run_scan(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    from backend.core.scheduler import run_manual_scan, log_event

    mode = settings.TRADING_MODE
    state = db.query(BotState).filter_by(mode=mode).first()
    if state:
        state.last_run = datetime.now(timezone.utc)
        db.commit()

    log_event("info", "Manual scan triggered (BTC + Weather)")
    await run_manual_scan()

    signals = await scan_for_signals()
    actionable = [s for s in signals if s.passes_threshold]

    result = {
        "status": "ok",
        "total_signals": len(signals),
        "actionable_signals": len(actionable),
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
            logger.warning("Failed to scan for weather signals in run_scan")
            result["weather_signals"] = 0
            result["weather_actionable"] = 0

    return result


# ============================================================================
# Decision Log Endpoints
# ============================================================================


_ALLOWED_DECISION_SORT = {
    "id",
    "created_at",
    "strategy",
    "market_ticker",
    "confidence",
    "decision",
}


@router.get("/api/decisions")
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
    _: None = Depends(require_admin),
):
    """List decision log entries with filtering."""
    if sort not in _ALLOWED_DECISION_SORT:
        sort = "created_at"
    limit = min(limit, 500)
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
        except ValueError as e:
            logger.debug(f"Strategy status check error: {e}")
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            query = query.filter(DecisionLog.created_at <= until_dt)
        except ValueError as e:
            logger.debug(f"Strategy status check error: {e}")
    total = query.count()
    col = getattr(DecisionLog, sort, DecisionLog.created_at)
    if order == "desc":
        col = col.desc()
    items = query.order_by(col).offset(offset).limit(limit).all()
    import json as _json

    def _parse_signal_data(raw):
        if not raw:
            return None
        try:
            return _json.loads(raw)
        except Exception:
            return raw

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
                "signal_data": _parse_signal_data(d.signal_data),
            }
            for d in items
        ],
        "total": total,
    }


@router.get("/api/decisions/export")
async def export_decisions(
    format: str = "jsonl",
    strategy: str | None = None,
    decision: str | None = None,
    limit: int = 10000,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Export decision log as JSONL for ML training."""
    limit = min(limit, 5000)
    from fastapi.responses import StreamingResponse
    import json as _json

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
                    logger.debug(
                        f"Failed to parse signal_data for decision {d.id}, using raw value"
                    )
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


@router.get("/api/decisions/{decision_id}")
async def get_decision(
    decision_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Get a single decision log entry by ID."""
    decision = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")

    signal_data = None
    if decision.signal_data:
        try:
            signal_data = _json.loads(decision.signal_data)
        except Exception:
            logger.debug(
                f"Failed to parse signal_data for decision {decision_id}, using raw value"
            )
            signal_data = decision.signal_data

    return {
        "id": decision.id,
        "strategy": decision.strategy,
        "market_ticker": decision.market_ticker,
        "decision": decision.decision,
        "confidence": decision.confidence,
        "signal_data": signal_data,
        "reason": decision.reason,
        "outcome": decision.outcome,
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
    }


# ============================================================================
# Signal Config Endpoint (public, no secrets)
# ============================================================================


@router.get("/api/signal-config")
async def get_signal_config():
    """Return current signal approval settings (no auth required, no secrets)."""
    return {
        "approval_mode": settings.SIGNAL_APPROVAL_MODE,
        "min_confidence": settings.AUTO_APPROVE_MIN_CONFIDENCE,
        "notification_duration_ms": settings.SIGNAL_NOTIFICATION_DURATION_MS,
    }


# ============================================================================
# Strategy Management Endpoints
# ============================================================================


@router.get("/api/strategies")
async def list_strategies(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """List all registered strategies with their DB config."""
    from backend.strategies.registry import STRATEGY_REGISTRY

    db_configs = {c.strategy_name: c for c in db.query(StrategyConfig).all()}

    # Map of strategy -> required credential keys
    STRATEGY_CREDENTIALS = {
        "kalshi_arb": ["KALSHI_API_KEY"],
        "copy_trader": ["POLYMARKET_PRIVATE_KEY"],
        "btc_oracle": [],  # uses public data only
        "btc_momentum": [],  # uses public data only
        "weather_emos": [],  # uses public weather data
        "general_market_scanner": [],
        "realtime_scanner": [],
        "whale_pnl_tracker": [],
        "bond_scanner": [],
        "market_maker": ["POLYMARKET_PRIVATE_KEY"],
    }

    result = []
    for name, cls in STRATEGY_REGISTRY.items():
        cfg = db_configs.get(name)
        required_creds = STRATEGY_CREDENTIALS.get(name, [])
        result.append(
            {
                "name": name,
                "description": getattr(cls, "description", ""),
                "category": getattr(cls, "category", "general"),
                "enabled": cfg.enabled if cfg else False,
                "interval_seconds": cfg.interval_seconds if cfg else 60,
                "params": _json.loads(cfg.params) if cfg and cfg.params else {},
                "default_params": dict(getattr(cls, "default_params", {})),
                "updated_at": cfg.updated_at.isoformat()
                if cfg and cfg.updated_at
                else None,
                "required_credentials": required_creds,
                "trading_mode": cfg.trading_mode if cfg else None,
            }
        )
    return result


class StrategyUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = None
    params: Optional[dict] = None
    trading_mode: Optional[str] = None


@router.get("/api/strategies/{name}")
async def get_strategy(
    name: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Get a single strategy config by name."""
    from backend.strategies.registry import STRATEGY_REGISTRY, load_all_strategies

    if not STRATEGY_REGISTRY:
        load_all_strategies()
    if name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    cfg = db.query(StrategyConfig).filter(StrategyConfig.strategy_name == name).first()
    try:
        inst = STRATEGY_REGISTRY[name]()
        description = getattr(inst, "description", name)
        category = getattr(inst, "category", "general")
        default_params = getattr(inst, "default_params", {})
    except Exception:
        description, category, default_params = name, "unknown", {}
    return {
        "name": name,
        "description": description,
        "category": category,
        "enabled": cfg.enabled if cfg else True,
        "interval_seconds": cfg.interval_seconds if cfg else 300,
        "params": _json.loads(cfg.params) if cfg and cfg.params else {},
        "default_params": default_params,
        "updated_at": cfg.updated_at.isoformat() if cfg and cfg.updated_at else None,
        "trading_mode": cfg.trading_mode if cfg else None,
    }


@router.put("/api/strategies/{name}")
async def update_strategy(
    name: str,
    body: StrategyUpdateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Update a strategy's config (enabled, interval, params)."""
    from backend.strategies.registry import STRATEGY_REGISTRY

    if name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    cfg = db.query(StrategyConfig).filter(StrategyConfig.strategy_name == name).first()
    if not cfg:
        cfg = StrategyConfig(strategy_name=name)
        db.add(cfg)

    if body.enabled is not None:
        cfg.enabled = body.enabled
    if body.interval_seconds is not None:
        cfg.interval_seconds = body.interval_seconds
    if body.params is not None:
        cfg.params = _json.dumps(body.params)
    if body.trading_mode is not None:
        valid_modes = ["paper", "testnet", "live", None]
        if body.trading_mode not in valid_modes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trading_mode '{body.trading_mode}'. Must be one of: paper, testnet, live",
            )
        cfg.trading_mode = body.trading_mode

    db.commit()
    db.refresh(cfg)

    # Reschedule the APScheduler job if interval changed or strategy was toggled
    if body.interval_seconds is not None or body.enabled is not None:
        from backend.core.scheduler import schedule_strategy, unschedule_strategy

        if cfg.enabled:
            schedule_strategy(name, cfg.interval_seconds or 60)
        else:
            unschedule_strategy(name)

    return {
        "name": name,
        "enabled": cfg.enabled,
        "interval_seconds": cfg.interval_seconds,
        "params": _json.loads(cfg.params) if cfg.params else {},
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
        "trading_mode": cfg.trading_mode,
    }


@router.post("/api/strategies/{name}/run-now")
async def run_strategy_now(name: str, _: None = Depends(require_admin)):
    """Trigger an immediate strategy run."""
    from backend.strategies.registry import STRATEGY_REGISTRY

    if name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    # Build a proper StrategyContext and run the strategy
    try:
        from backend.strategies.base import StrategyContext
        from backend.models.database import SessionLocal, BotState, StrategyConfig

        cls = STRATEGY_REGISTRY[name]
        instance = cls()
        db = SessionLocal()
        try:
            cfg = (
                db.query(StrategyConfig)
                .filter(StrategyConfig.strategy_name == name)
                .first()
            )
            strategy_mode = (
                cfg.trading_mode if cfg and cfg.trading_mode else None
            ) or settings.TRADING_MODE
            
            state = db.query(BotState).filter_by(mode=strategy_mode).first()
            if not state:
                raise HTTPException(status_code=404, detail="Bot state not initialized")
            cfg = (
                db.query(StrategyConfig)
                .filter(StrategyConfig.strategy_name == name)
                .first()
            )
            strategy_mode = (
                cfg.trading_mode if cfg and cfg.trading_mode else None
            ) or settings.TRADING_MODE
            ctx = StrategyContext(
                db=db,
                clob=None,
                settings=settings,
                logger=logger,
                params=dict(getattr(cls, "default_params", {})),
                mode=strategy_mode,
            )
            result = await instance.run(ctx)

            buy_decisions = [
                d
                for d in getattr(result, "decisions", [])
                if isinstance(d, dict)
                and d.get("decision") == "BUY"
                and d.get("market_ticker")
            ]

            if buy_decisions:
                from backend.core.strategy_executor import execute_decisions

                execution_modes = []
                if strategy_mode == "live":
                    execution_modes = ["paper", "live"]
                else:
                    execution_modes = [strategy_mode]

                for mode in execution_modes:
                    decisions_copy = [d.copy() for d in buy_decisions]
                    for d in decisions_copy:
                        d["trading_mode"] = mode
                    await execute_decisions(decisions_copy, name, db=db)

        finally:
            db.close()

        return {
            "status": "ok",
            "name": name,
            "decisions": result.decisions_recorded,
            "trades_attempted": result.trades_attempted,
            "errors": len(result.errors),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual run of strategy '{name}' failed: {e}")
        raise HTTPException(
            status_code=500, detail="Strategy run failed — check server logs"
        )
