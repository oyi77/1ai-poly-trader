"""TradeForensics to AGI improvement integration — feeds loss patterns into proposals."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, StrategyProposal, Trade

logger = logging.getLogger("trading_bot.forensics_integration")


def generate_forensics_proposals(
    lookback_hours: int = 168,
    min_losses: int = 5,
    db: Optional[Session] = None,
) -> list[int]:
    _owned = db is None
    db = db or SessionLocal()
    created_ids = []
    try:
        from backend.core.trade_forensics import trade_forensics
        from backend.models.outcome_tables import StrategyOutcome

        cutoff = datetime.now(timezone.utc)
        from datetime import timedelta

        since = cutoff - timedelta(hours=lookback_hours)

        outcomes = (
            db.query(StrategyOutcome)
            .filter(
                StrategyOutcome.result == "loss",
                StrategyOutcome.settled_at >= since,
            )
            .all()
        )

        by_strategy: dict[str, list] = {}
        for o in outcomes:
            by_strategy.setdefault(o.strategy, []).append(o)

        for strategy_name, losses in by_strategy.items():
            if len(losses) < min_losses:
                continue

            total_loss = sum(abs(o.pnl or 0.0) for o in losses)
            existing = db.query(StrategyProposal).filter(
                StrategyProposal.strategy_name == strategy_name,
                StrategyProposal.status == "pending",
            ).first()
            if existing:
                continue

            proposal = StrategyProposal(
                strategy_name=strategy_name,
                change_details={
                    "source": "trade_forensics",
                    "loss_count": len(losses),
                    "total_loss": round(total_loss, 2),
                    "lookback_hours": lookback_hours,
                },
                expected_impact=(
                    f"Forensics: {len(losses)} losses (${total_loss:.2f}) in "
                    f"{lookback_hours}h — review and adjust parameters"
                ),
                admin_decision="pending",
                status="pending",
                auto_promotable=False,
            )
            db.add(proposal)
            db.flush()
            created_ids.append(proposal.id)

        if created_ids:
            db.commit()
            logger.info(
                "[ForensicsIntegration] Created %d forensics-based proposals",
                len(created_ids),
            )
        return created_ids
    except Exception as e:
        logger.error("[ForensicsIntegration] Failed: %s", e)
        if _owned:
            try:
                db.rollback()
            except Exception:
                pass
        return created_ids
    finally:
        if _owned:
            db.close()
