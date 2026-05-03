import json
import logging
import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, StrategyConfig
from backend.models.outcome_tables import StrategyOutcome
from backend.models.kg_models import ExperimentRecord
from backend.core.agi_types import ExperimentStatus

logger = logging.getLogger("trading_bot.evolver")

TUNABLE_PARAM_RANGES = {
    "min_edge": (0.01, 0.20),
    "max_position_usd": (5.0, 100.0),
    "interval_seconds": (15, 300),
    "max_minutes_to_resolution": (10, 120),
}

EVOLVABLE_WIN_RATE_FLOOR = 0.05
EVOLVABLE_WIN_RATE_CEIL = 0.35
MIN_OUTCOMES_TO_EVOLVE = 10
FUNDAMENTALLY_BROKEN_WIN_RATE = 0.0
FUNDAMENTALLY_BROKEN_MIN_TRADES = 30
VARIANTS_PER_STRATEGY = 3
PARAM_PERTURBATION = 0.25


class StrategyEvolver:
    def run_evolution_cycle(self, db: Optional[Session] = None) -> list[int]:
        _owned = db is None
        db = db or SessionLocal()
        created = []
        try:
            strategies = self._find_evolvable_strategies(db)
            for strategy_name, stats in strategies.items():
                if self._has_active_experiment(strategy_name, db):
                    continue
                variants = self._generate_variants(strategy_name, db)
                for variant in variants:
                    exp = ExperimentRecord(
                        name=f"{strategy_name}_evolve_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}_{random.randint(1000,9999)}",
                        strategy_name=strategy_name,
                        strategy_composition=variant,
                        status=ExperimentStatus.DRAFT.value,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(exp)
                    created.append(exp.id if exp.id else 0)
            if created:
                db.commit()
                logger.info(
                    "[StrategyEvolver] Created %d variant experiments for %d strategies",
                    len(created),
                    len(strategies),
                )
            return created
        except Exception as e:
            logger.error("[StrategyEvolver] Failed: %s", e)
            if _owned:
                try:
                    db.rollback()
                except Exception:
                    pass
            return created
        finally:
            if _owned:
                db.close()

    def _find_evolvable_strategies(self, db: Session) -> dict:
        from sqlalchemy import func
        rows = (
            db.query(
                StrategyOutcome.strategy,
                func.count(StrategyOutcome.id).label("total"),
            )
            .group_by(StrategyOutcome.strategy)
            .all()
        )
        result = {}
        for row in rows:
            name = row.strategy
            total = row.total
            if total < MIN_OUTCOMES_TO_EVOLVE:
                continue
            outcomes = (
                db.query(StrategyOutcome)
                .filter(StrategyOutcome.strategy == name)
                .all()
            )
            wins = sum(1 for o in outcomes if o.result == "win")
            wr = wins / total if total > 0 else 0.0
            if total >= FUNDAMENTALLY_BROKEN_MIN_TRADES and wr <= FUNDAMENTALLY_BROKEN_WIN_RATE:
                logger.info(
                    "[StrategyEvolver] Skipping '%s' — fundamentally broken (%d trades, %.1f%% WR)",
                    name, total, wr * 100,
                )
                continue
            if EVOLVABLE_WIN_RATE_FLOOR <= wr < EVOLVABLE_WIN_RATE_CEIL:
                result[name] = {"total": total, "wins": wins, "win_rate": wr}
        return result

    def _has_active_experiment(self, strategy_name: str, db: Session) -> bool:
        active_statuses = [
            ExperimentStatus.DRAFT.value,
            ExperimentStatus.SHADOW.value,
            ExperimentStatus.PAPER.value,
        ]
        return (
            db.query(ExperimentRecord)
            .filter(
                ExperimentRecord.strategy_name == strategy_name,
                ExperimentRecord.status.in_(active_statuses),
            )
            .first()
            is not None
        )

    def _generate_variants(self, strategy_name: str, db: Session) -> list[dict]:
        config = (
            db.query(StrategyConfig)
            .filter(StrategyConfig.strategy_name == strategy_name)
            .first()
        )
        base_params = {}
        if config and config.params:
            try:
                base_params = json.loads(config.params) if isinstance(config.params, str) else config.params
            except (json.JSONDecodeError, TypeError):
                base_params = {}

        from backend.strategies.registry import STRATEGY_REGISTRY
        strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
        if strategy_cls and hasattr(strategy_cls, "default_params"):
            for k, v in strategy_cls.default_params.items():
                base_params.setdefault(k, v)

        variants = []
        for i in range(VARIANTS_PER_STRATEGY):
            variant = dict(base_params)
            variant["_evolver_generation"] = i + 1
            variant["_evolver_created_at"] = datetime.now(timezone.utc).isoformat()
            for param_key, (lo, hi) in TUNABLE_PARAM_RANGES.items():
                if param_key in variant:
                    current = float(variant[param_key])
                    perturbation = current * PARAM_PERTURBATION * random.choice([-1, 1])
                    new_val = max(lo, min(hi, current + perturbation))
                    if isinstance(variant[param_key], int):
                        new_val = int(round(new_val))
                    variant[param_key] = round(new_val, 4) if isinstance(new_val, float) else new_val
            variants.append(variant)
        return variants
