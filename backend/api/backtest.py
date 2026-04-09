"""
Backtesting API endpoints for PolyEdge strategy evaluation.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

from backend.models.database import get_db, SessionLocal, Trade, Signal
from backend.models.backtest import BacktestRun, BacktestTrade
from backend.strategies.registry import BaseStrategy, STRATEGY_REGISTRY, load_all_strategies


def get_all_strategies() -> dict:
    if not STRATEGY_REGISTRY:
        load_all_strategies()
    return dict(STRATEGY_REGISTRY)


# Alias for signal model used in queries
SignalHistoryRow = Signal

router = APIRouter()

# Note: /api/backtest/run and /api/backtest/quick are in system.py to avoid duplicates.

@router.get("/api/backtest/strategies")
async def get_backtest_strategies():
    """Get all available strategies for backtesting."""
    strategies = get_all_strategies()
    result = []
    for name, strategy_class in strategies.items():
        try:
            inst = strategy_class()
            result.append({
                "name": name,
                "description": getattr(inst, "description", name),
                "category": getattr(inst, "category", "general"),
                "default_params": getattr(inst, "default_params", {}),
            })
        except Exception:
            result.append({
                "name": name,
                "description": name,
                "category": "unknown",
                "default_params": {},
            })
    return {"strategies": result}

@router.get("/api/backtest/history")
async def get_backtest_history(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get history of backtest runs."""
    # This would query a BacktestRun table if we had one
    # For now, return placeholder
    return {
        "runs": [],
        "total": 0,
        "limit": limit,
        "offset": offset
    }

async def run_backtest_engine(
    strategy: BaseStrategy,
    db: Session,
    start_date: datetime,
    end_date: datetime,
    initial_bankroll: float,
    params: Dict[str, Any],
    run_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Core backtesting engine.
    """
    # Get historical signals for the date range
    historical_signals = get_historical_signals(db, strategy.name, start_date, end_date)

    # Initialize backtest state
    current_bankroll = initial_bankroll
    portfolio_value = [initial_bankroll]
    trade_log = []
    equity_curve = []

    # Simulate each signal
    for signal in historical_signals:
        # Calculate Kelly size
        kelly_size = calculate_kelly_size(
            edge=signal['edge'],
            bankroll=current_bankroll,
            max_bankroll_pct=0.15  # 15% max bankroll per trade
        )

        # Execute trade
        trade_result = await execute_backtest_trade(
            strategy=strategy,
            signal=signal,
            size=kelly_size,
            current_bankroll=current_bankroll
        )

        # Update state
        current_bankroll += trade_result['pnl']
        portfolio_value.append(current_bankroll)

        # Record trade
        trade_result_record = {
            **trade_result,
            'timestamp': signal['timestamp'],
            'signal_id': signal['id'],
            'bankroll_after_trade': current_bankroll
        }
        trade_log.append(trade_result_record)

        # Save to database if run_id is provided
        if run_id:
            backtest_trade = BacktestTrade(
                run_id=run_id,
                signal_id=signal['id'],
                market_ticker=signal['market_ticker'],
                platform=signal['platform'],
                direction=signal['direction'],
                entry_price=trade_result['entry_price'],
                exit_price=trade_result['exit_price'],
                size=trade_result['size'],
                pnl=trade_result['pnl'],
                result=trade_result['result'],
                edge_at_entry=signal['edge'],
                market_probability_at_entry=signal.get('market_probability'),
                model_probability_at_entry=signal.get('model_probability'),
                timestamp=datetime.fromisoformat(signal['timestamp']),
                executed=signal.get('executed', False)
            )
            db.add(backtest_trade)

        equity_curve.append({
            'timestamp': signal['timestamp'],
            'equity': current_bankroll,
            'pnl': current_bankroll - initial_bankroll
        })

    # Commit all trades to database
    if run_id:
        db.commit()

    # Calculate performance metrics
    final_equity = current_bankroll
    total_pnl = final_equity - initial_bankroll
    total_return = total_pnl / initial_bankroll * 100

    winning_trades = len([t for t in trade_log if t['pnl'] > 0])
    losing_trades = len([t for t in trade_log if t['pnl'] < 0])
    total_trades = len(trade_log)

    win_rate = winning_trades / total_trades if total_trades > 0 else 0

    # Sharpe ratio calculation (simplified)
    returns = np.diff(portfolio_value)
    sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(365 * 24 * 60) if len(returns) > 1 else 0  # minute-level data

    return {
        "summary": {
            "total_signals": len(historical_signals),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "initial_bankroll": initial_bankroll,
            "final_equity": final_equity,
            "total_pnl": total_pnl,
            "total_return_pct": total_return,
            "sharpe_ratio": sharpe_ratio
        },
        "trade_log": trade_log,
        "equity_curve": equity_curve,
        "signals_processed": len(historical_signals)
    }

def get_historical_signals(
    db: Session,
    strategy_name: str,
    start_date: datetime,
    end_date: datetime
) -> List[Dict[str, Any]]:
    """
    Get historical signals for a strategy in the given date range.
    """
    query = db.query(SignalHistoryRow).filter(
        SignalHistoryRow.timestamp.between(start_date, end_date),
        SignalHistoryRow.market_type.in_(['btc', 'weather'])
    )

    if strategy_name:
        # Filter by strategy if specified
        query = query.filter(SignalHistoryRow.reasoning.contains(strategy_name))

    signals = query.all()

    # Convert to dict format
    historical_signals = []
    for signal in signals:
        historical_signals.append({
            'id': signal.id,
            'market_ticker': signal.market_ticker,
            'platform': signal.platform,
            'market_type': signal.market_type,
            'direction': signal.direction,
            'model_probability': signal.model_probability,
            'market_probability': signal.market_probability,
            'edge': signal.edge,
            'confidence': signal.confidence,
            'suggested_size': signal.suggested_size,
            'reasoning': signal.reasoning,
            'timestamp': signal.timestamp,
            'executed': signal.executed,
            'actual_outcome': signal.actual_outcome,
            'outcome_correct': signal.outcome_correct,
            'settlement_value': signal.settlement_value
        })

    return historical_signals

def calculate_kelly_size(edge: float, bankroll: float, max_bankroll_pct: float = 0.15) -> float:
    """
    Calculate Kelly Criterion position size.
    """
    if edge <= 0:
        return 0

    # Kelly fraction: f = (bp - q) / b
    # Where b = odds received, p = probability of win, q = probability of loss
    # For binary options, b = 1 (payout is 1:1)
    kelly_fraction = edge

    # Apply maximum size constraint
    max_size = bankroll * max_bankroll_pct
    kelly_size = bankroll * kelly_fraction

    return min(kelly_size, max_size)

async def execute_backtest_trade(
    strategy: BaseStrategy,
    signal: Dict[str, Any],
    size: float,
    current_bankroll: float
) -> Dict[str, Any]:
    """
    Simulate executing a trade and calculate P&L.
    """
    # Get settlement value (0.0 for Down win, 1.0 for Up win)
    settlement_value = signal.get('settlement_value')

    if settlement_value is None:
        # Trade hasn't settled yet, use actual_outcome if available
        if signal.get('actual_outcome'):
            settlement_value = 1.0 if signal['actual_outcome'] == signal['direction'] else 0.0
        else:
            # Cannot determine outcome, skip
            return {
                'entry_price': signal.get('market_probability', 0.5),
                'exit_price': None,
                'size': size,
                'pnl': 0,
                'result': 'pending',
                'edge_at_entry': signal.get('edge', 0)
            }

    # Calculate P&L
    if signal['direction'] == 'up':
        if settlement_value == 1.0:  # Up won
            pnl = size * (1 - signal.get('market_probability', 0.5))
            result = 'win'
        else:  # Down won
            pnl = -size
            result = 'loss'
    else:  # down
        if settlement_value == 0.0:  # Down won
            pnl = size * (1 - signal.get('market_probability', 0.5))
            result = 'win'
        else:  # Up won
            pnl = -size
            result = 'loss'

    return {
        'entry_price': signal.get('market_probability', 0.5),
        'exit_price': settlement_value,
        'size': size,
        'pnl': pnl,
        'result': result,
        'edge_at_entry': signal.get('edge', 0)
    }