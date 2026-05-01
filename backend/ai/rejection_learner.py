"""Rejection Learner — feeds TradeAttempt rejection patterns back into strategy parameters.

Reads blocked/rejected TradeAttempts, identifies systematic rejection causes per strategy,
and generates targeted proposals to fix the root cause.

Example: if strategy X keeps hitting ORDER_TOO_SMALL, this module proposes increasing
kelly_fraction or lowering min_edge threshold so future trades exceed the minimum order size.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from sqlalchemy.sql import func

from backend.models.database import SessionLocal, TradeAttempt, StrategyConfig, StrategyProposal

logger = logging.getLogger("trading_bot.rejection_learner")

LOOKBACK_DAYS = 7
MIN_REJECTIONS = 10

REJECTION_ADJUSTMENTS = {
    "REJECTED_DRAWDOWN_BREAKER": {
        "description": "Strategy hitting drawdown limit too often — reduce position sizing",
        "param_adjustments": {"kelly_fraction": 0.7},
    },
    "REJECTED_LOW_CONFIDENCE": {
        "description": "Confidence below threshold — lower confidence requirement or improve signal quality",
        "param_adjustments": {"confidence_threshold": 0.85},
    },
    "REJECTED_MAX_EXPOSURE": {
        "description": "Portfolio over-concentrated — reduce max exposure per trade",
        "param_adjustments": {"max_position_fraction": 0.7, "max_total_exposure": 0.85},
    },
    "REJECTED_ORDER_TOO_SMALL": {
        "description": "Trade size below exchange minimum — increase kelly fraction or minimum edge",
        "param_adjustments": {"kelly_fraction": 1.8, "min_edge": 0.04},
    },
    "BLOCKED_DUPLICATE_OPEN_POSITION": {
        "description": "Repeated duplicate positions — increase cooldown or reduce per-market frequency",
        "param_adjustments": {"cooldown_minutes": 1.5},
    },
    "REJECTED_BROKER_ORDER": {
        "description": "Exchange rejecting orders — check token/liquidity/size issues",
        "param_adjustments": {"slippage_buffer": 1.5},
    },
    "BLOCKED_NO_EXECUTION_CONTEXT": {
        "description": "Bot not in proper state to execute — check orchestrator lifecycle",
        "param_adjustments": {},
    },
}


def analyze_rejections(lookback_days: int = LOOKBACK_DAYS) -> Dict[str, Dict]:
    """Analyze TradeAttempt rejections grouped by (strategy, reason_code).

    Returns dict keyed by strategy_name, each containing:
    - top rejection reasons with counts
    - total rejection count
    - total attempt count (for context)
    """
    db = SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        rejected = db.query(
            TradeAttempt.strategy,
            TradeAttempt.reason_code,
            TradeAttempt.status,
            func.count(TradeAttempt.id).label("cnt"),
            func.avg(TradeAttempt.requested_size).label("avg_size"),
            func.avg(TradeAttempt.confidence).label("avg_conf"),
            func.avg(TradeAttempt.edge).label("avg_edge"),
        ).filter(
            TradeAttempt.status.in_(["BLOCKED", "REJECTED", "FAILED"]),
            TradeAttempt.created_at >= since,
        ).group_by(
            TradeAttempt.strategy,
            TradeAttempt.reason_code,
            TradeAttempt.status,
        ).order_by(func.count(TradeAttempt.id).desc()).all()

        total_attempts = db.query(func.count(TradeAttempt.id)).filter(
            TradeAttempt.created_at >= since
        ).scalar() or 1

        strategies: Dict[str, Dict] = {}
        for row in rejected:
            strat = row.strategy or "unknown"
            if strat not in strategies:
                strategies[strat] = {
                    "rejections": [],
                    "total_rejections": 0,
                    "total_attempts": total_attempts,
                }
            strategies[strat]["rejections"].append({
                "reason_code": row.reason_code,
                "status": row.status,
                "count": row.cnt,
                "avg_size": float(row.avg_size or 0),
                "avg_conf": float(row.avg_conf or 0),
                "avg_edge": float(row.avg_edge or 0),
            })
            strategies[strat]["total_rejections"] += row.cnt

        return strategies
    except Exception as e:
        logger.warning(f"Rejection analysis failed: {e}")
        return {}
    finally:
        db.close()


def generate_rejection_proposals(min_rejections: int = MIN_REJECTIONS) -> List[str]:
    """Generate StrategyProposals from systematic rejection patterns.

    For each strategy with > min_rejections of a single reason code that maps to
    a known adjustment, create a proposal to adjust the relevant parameters.

    Returns list of proposal descriptions created.
    """
    db = SessionLocal()
    created: List[str] = []
    try:
        analysis = analyze_rejections()

        for strategy_name, data in analysis.items():
            if data["total_rejections"] < min_rejections:
                continue

            for rej in data["rejections"]:
                reason_code = rej["reason_code"]
                count = rej["count"]
                if count < min_rejections:
                    continue

                adjustment = REJECTION_ADJUSTMENTS.get(reason_code)
                if not adjustment:
                    continue

                param_changes = adjustment["param_adjustments"]
                if not param_changes:
                    continue

                existing = db.query(StrategyProposal).filter(
                    StrategyProposal.strategy_name == strategy_name,
                    StrategyProposal.status == "pending",
                    StrategyProposal.reason_code if hasattr(StrategyProposal, 'reason_code') else True,
                ).first()

                cfg = db.query(StrategyConfig).filter(
                    StrategyConfig.strategy_name == strategy_name
                ).first()

                current_params = (cfg.params if cfg and cfg.params else {}) or {}
                proposed = {}
                for key, multiplier in param_changes.items():
                    current_val = current_params.get(key)
                    if current_val is not None and isinstance(current_val, (int, float)):
                        proposed[key] = round(float(current_val) * multiplier, 6)
                    elif current_val is None:
                        proposed[key] = round(multiplier, 6)

                if not proposed:
                    continue

                proposal = StrategyProposal(
                    strategy_name=strategy_name,
                    change_details=proposed,
                    expected_impact=(
                        f"{adjustment['description']} "
                        f"(reason: {reason_code}, occurrences: {count}, "
                        f"avg_size: {rej['avg_size']:.2f}, avg_conf: {rej['avg_conf']:.2f})"
                    ),
                    admin_decision="pending",
                    status="pending",
                    auto_promotable=True,
                    proposed_params=proposed,
                )
                db.add(proposal)
                created.append(f"{strategy_name}: {reason_code} → {proposed}")

        if created:
            db.commit()
            logger.info(f"Rejection learner: created {len(created)} proposals from rejection patterns")
    except Exception as e:
        logger.warning(f"Rejection proposal generation failed: {e}")
        db.rollback()
    finally:
        db.close()

    return created