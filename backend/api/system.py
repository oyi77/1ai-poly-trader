"""System routes - stats, bot control, backtest, events."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
import json as _json

from backend.config import settings
from backend.models.database import get_db, BotState, Trade, Signal, AILog, DecisionLog, StrategyConfig, SessionLocal
from backend.api.auth import require_admin
from backend.core.signals import scan_for_signals
import logging

logger = logging.getLogger("trading_bot")

router = APIRouter(tags=["system"])


# ============================================================================
# Pydantic Response Models
# ============================================================================


class BotStats(BaseModel):
    bankroll: float
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl: float
    is_running: bool
    last_run: Optional[datetime]
    # Initial bankroll for return calculation
    initial_bankroll: float = 10000.0
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


class EventResponse(BaseModel):
    timestamp: str
    type: str
    message: str
    data: dict = {}


# ============================================================================
# Stats Endpoint
# ============================================================================


@router.get("/api/stats", response_model=BotStats)
async def get_stats(db: Session = Depends(get_db)):
    state = db.query(BotState).first()
    if not state:
        raise HTTPException(status_code=404, detail="Bot state not initialized")

    # Paper stats
    paper_pnl = state.paper_pnl or 0.0
    paper_bankroll = state.paper_bankroll or settings.INITIAL_BANKROLL
    paper_trades = state.paper_trades or 0
    paper_wins = state.paper_wins or 0
    paper_win_rate = paper_wins / paper_trades if paper_trades > 0 else 0.0

    # Live stats
    live_pnl = state.total_pnl or 0.0
    live_bankroll = state.bankroll or settings.INITIAL_BANKROLL
    live_trades = state.total_trades or 0
    live_wins = state.winning_trades or 0
    live_win_rate = live_wins / live_trades if live_trades > 0 else 0.0

    # Fallback: if mode PnL is 0 but settled trades exist, recalculate from DB
    pnl_source = "botstate"
    mode = settings.TRADING_MODE
    if mode == "paper" and paper_pnl == 0 and paper_trades > 0:
        db_pnl = db.query(func.sum(Trade.pnl)).filter(Trade.settled == True).scalar() or 0.0
        if db_pnl != 0:
            paper_pnl = db_pnl
            pnl_source = "recalculated"

    # Top-level fields reflect the ACTIVE trading mode
    if mode == "paper":
        display_bankroll = paper_bankroll
        display_trades = paper_trades
        display_wins = paper_wins
        display_win_rate = paper_win_rate
        display_pnl = paper_pnl
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
        mode=mode,
        pnl_source=pnl_source,
        paper={
            "pnl": paper_pnl,
            "bankroll": paper_bankroll,
            "trades": paper_trades,
            "wins": paper_wins,
            "win_rate": paper_win_rate,
        },
        live={
            "pnl": live_pnl,
            "bankroll": live_bankroll,
            "trades": live_trades,
            "wins": live_wins,
            "win_rate": live_win_rate,
        },
    )


# ============================================================================
# AI Status & Control
# ============================================================================


@router.get("/api/stats/strategies")
async def get_strategy_stats(db: Session = Depends(get_db)):
    """Return P&L breakdown per strategy."""
    from sqlalchemy import case

    results = db.query(
        Trade.strategy,
        func.count(Trade.id).label("total_trades"),
        func.sum(case((Trade.result == "win", 1), else_=0)).label("wins"),
        func.sum(case((Trade.result == "loss", 1), else_=0)).label("losses"),
        func.sum(case((Trade.settled == True, Trade.pnl), else_=0)).label("total_pnl"),
        func.avg(Trade.edge_at_entry).label("avg_edge"),
        func.avg(Trade.size).label("avg_size"),
    ).filter(
        Trade.strategy.isnot(None)
    ).group_by(Trade.strategy).all()

    strategies = []
    for r in results:
        total = r.wins + r.losses
        strategies.append({
            "strategy": r.strategy or "unknown",
            "total_trades": r.total_trades,
            "wins": r.wins,
            "losses": r.losses,
            "pending": r.total_trades - r.wins - r.losses,
            "win_rate": r.wins / total if total > 0 else 0,
            "total_pnl": round(r.total_pnl or 0, 2),
            "avg_edge": round(r.avg_edge or 0, 4),
            "avg_size": round(r.avg_size or 0, 2),
        })

    return {"strategies": sorted(strategies, key=lambda s: s["total_pnl"], reverse=True)}


@router.get("/api/ai/status")
async def get_ai_status(db: Session = Depends(get_db)):
    """Return AI system status: enabled, provider, budget usage."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    spent_today = db.query(func.coalesce(func.sum(AILog.cost_usd), 0.0)).filter(
        AILog.timestamp >= today_start
    ).scalar() or 0.0
    calls_today = db.query(func.count(AILog.id)).filter(
        AILog.timestamp >= today_start
    ).scalar() or 0

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


@router.post("/api/bot/stop")
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


@router.post("/api/bot/reset")
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
            state.paper_bankroll = settings.INITIAL_BANKROLL
            state.paper_trades = 0
            state.paper_wins = 0
            state.paper_pnl = 0.0
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


@router.post("/api/backtest/run")
async def run_backtest_frontend(
    body: FrontendBacktestRequest, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Run backtest against historical signals - matches frontend API contract."""
    from backend.core.backtesting import BacktestEngine, BacktestConfig

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


@router.post("/api/backtest")
async def run_backtest(
    body: BacktestRequest, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Run backtest against historical signals."""
    from backend.core.backtesting import BacktestEngine, BacktestConfig

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


# ============================================================================
# Events Endpoints
# ============================================================================


@router.get("/api/events", response_model=List[EventResponse])
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


@router.post("/api/run-scan")
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
            logger.warning("Failed to scan for weather signals in run_scan")
            result["weather_signals"] = 0
            result["weather_actionable"] = 0

    return result


# ============================================================================
# Decision Log Endpoints
# ============================================================================


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


@router.get("/api/decisions/export")
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
                    logger.debug(f"Failed to parse signal_data for decision {d.id}, using raw value")
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
async def get_decision(decision_id: int, db: Session = Depends(get_db)):
    """Get a single decision log entry by ID."""
    decision = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")

    signal_data = None
    if decision.signal_data:
        try:
            signal_data = _json.loads(decision.signal_data)
        except Exception:
            logger.debug(f"Failed to parse signal_data for decision {decision_id}, using raw value")
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
async def list_strategies(db: Session = Depends(get_db)):
    """List all registered strategies with their DB config."""
    from backend.strategies.registry import STRATEGY_REGISTRY

    db_configs = {c.strategy_name: c for c in db.query(StrategyConfig).all()}

    result = []
    for name, cls in STRATEGY_REGISTRY.items():
        cfg = db_configs.get(name)
        result.append({
            "name": name,
            "description": getattr(cls, "description", ""),
            "category": getattr(cls, "category", "general"),
            "enabled": cfg.enabled if cfg else False,
            "interval_seconds": cfg.interval_seconds if cfg else 60,
            "params": _json.loads(cfg.params) if cfg and cfg.params else {},
            "default_params": dict(getattr(cls, "default_params", {})),
            "updated_at": cfg.updated_at.isoformat() if cfg and cfg.updated_at else None,
        })
    return result


class StrategyUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = None
    params: Optional[dict] = None


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

    db.commit()
    db.refresh(cfg)

    return {
        "name": name,
        "enabled": cfg.enabled,
        "interval_seconds": cfg.interval_seconds,
        "params": _json.loads(cfg.params) if cfg.params else {},
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.post("/api/strategies/{name}/run-now")
async def run_strategy_now(name: str, _: None = Depends(require_admin)):
    """Trigger an immediate strategy run."""
    from backend.strategies.registry import STRATEGY_REGISTRY

    if name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    # Run the strategy's scan method if available
    try:
        cls = STRATEGY_REGISTRY[name]
        instance = cls()
        if hasattr(instance, 'scan'):
            await instance.scan()
        elif hasattr(instance, 'run'):
            await instance.run()
        else:
            return {"status": "no_scan_method", "name": name}
    except Exception as e:
        logger.error(f"Manual run of strategy '{name}' failed: {e}")
        raise HTTPException(status_code=500, detail=f"Strategy run failed: {e}")

    return {"status": "ok", "name": name}
