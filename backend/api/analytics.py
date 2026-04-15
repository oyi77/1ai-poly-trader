"""Analytics API endpoints — strategy metrics, equity curve, calibration, experiments."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal

logger = logging.getLogger("trading_bot.analytics")

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/strategies")
def get_strategy_metrics(
    lookback_days: int = Query(30, ge=1, le=365),
    min_trades: int = Query(5, ge=1),
    db: Session = Depends(get_db),
):
    """Get per-strategy performance metrics ranked by risk-adjusted return."""
    from backend.core.strategy_ranker import strategy_ranker

    ranked = strategy_ranker.rank_all(
        db, lookback_days=lookback_days, min_trades=min_trades
    )

    return {
        "lookback_days": lookback_days,
        "strategies": [
            {
                "name": r.name,
                "rank_score": r.rank_score,
                "total_trades": r.total_trades,
                "winning_trades": r.winning_trades,
                "win_rate": r.win_rate,
                "total_pnl": r.total_pnl,
                "sharpe_ratio": r.sharpe_ratio,
                "sortino_ratio": r.sortino_ratio,
                "profit_factor": r.profit_factor,
                "max_drawdown": r.max_drawdown,
                "avg_return": r.avg_return,
            }
            for r in ranked
        ],
    }


@router.get("/equity-curve")
def get_equity_curve(
    limit: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get historical equity curve snapshots."""
    from backend.models.database import EquitySnapshot

    snapshots = (
        db.query(EquitySnapshot)
        .order_by(EquitySnapshot.timestamp.desc())
        .limit(limit)
        .all()
    )

    return {
        "snapshots": [
            {
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                "bankroll": s.bankroll,
                "total_pnl": s.total_pnl,
                "open_exposure": s.open_exposure,
                "trade_count": s.trade_count,
                "win_count": s.win_count,
            }
            for s in reversed(snapshots)
        ]
    }


@router.get("/calibration/{strategy}")
def get_calibration(
    strategy: str,
    num_bins: int = Query(10, ge=3, le=20),
    db: Session = Depends(get_db),
):
    """Get model calibration curve for a strategy."""
    from backend.core.calibration_tracker import calibration_tracker

    summary = calibration_tracker.get_strategy_summary(db, strategy=strategy)
    return summary


@router.get("/calibration")
def get_calibration_all(
    num_bins: int = Query(10, ge=3, le=20),
    db: Session = Depends(get_db),
):
    """Get model calibration curve across all strategies."""
    from backend.core.calibration_tracker import calibration_tracker

    summary = calibration_tracker.get_strategy_summary(db, strategy=None)
    return summary


@router.get("/experiments")
def get_experiments(
    strategy: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get experiment history for a strategy or all strategies."""
    from backend.core.experiment_tracker import experiment_tracker

    history = experiment_tracker.get_history(db, strategy_name=strategy, limit=limit)
    return {"experiments": history}


@router.get("/experiments/{experiment_id}/compare/{other_id}")
def compare_experiments(
    experiment_id: int,
    other_id: int,
    db: Session = Depends(get_db),
):
    """Compare two experiments."""
    from backend.core.experiment_tracker import experiment_tracker

    result = experiment_tracker.compare(db, experiment_id, other_id)
    return result


@router.get("/allocations")
def get_allocations(
    lookback_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get recommended bankroll allocations across strategies."""
    from backend.core.strategy_ranker import strategy_ranker
    from backend.models.database import BotState
    from backend.config import settings

    state = db.query(BotState).first()
    bankroll = settings.INITIAL_BANKROLL
    if state:
        if settings.TRADING_MODE == "paper":
            bankroll = float(
                state.paper_bankroll
                if state.paper_bankroll is not None
                else settings.INITIAL_BANKROLL
            )
        elif settings.TRADING_MODE == "testnet":
            bankroll = float(
                state.testnet_bankroll
                if state.testnet_bankroll is not None
                else settings.INITIAL_BANKROLL
            )
        else:
            bankroll = float(
                state.bankroll
                if state.bankroll is not None
                else settings.INITIAL_BANKROLL
            )

    allocations = strategy_ranker.auto_allocate(db, bankroll, lookback_days)
    return {
        "bankroll": bankroll,
        "lookback_days": lookback_days,
        "allocations": allocations,
    }
