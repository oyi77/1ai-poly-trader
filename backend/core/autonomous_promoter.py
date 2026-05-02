"""Autonomous Promoter — fully automatic experiment lifecycle management.

This daemon runs periodically (default every 6h) and:
- Evaluates all DRAFT experiments → promotes to SHADOW immediately
- Evaluates all SHADOW experiments → promotes to PAPER if criteria met
- Evaluates all PAPER experiments → promotes to LIVE if criteria met AND config allows
- Retires failed experiments (no activity, chronically poor metrics)
- Optionally auto-enables strategies in StrategyConfig upon LIVE promotion

Respects ADR-006 gate but can be overridden via AGI_AUTO_PROMOTE=true.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.config import settings
from backend.models.database import SessionLocal, StrategyConfig, BotState
from backend.models.kg_models import ExperimentRecord
from backend.core.experiment_runner import ExperimentRunner, EvaluationResult
from backend.core.agi_types import ExperimentStatus
from backend.core.strategy_health import StrategyHealthMonitor

logger = logging.getLogger("trading_bot.autonomous_promoter")


class AutonomousPromoter:
    """Daemon that evaluates and promotes experiments without human intervention."""

    # Shadow → Paper criteria (matches AGIPromotionPipeline defaults)
    MIN_TRADES_SHADOW = 100
    MIN_DAYS_SHADOW = 7
    MIN_WIN_RATE_SHADOW = 0.45
    MAX_DRAWDOWN_SHADOW = 0.25  # Not yet enforced in ExperimentRunner.evaluate (TODO)

    # Paper → Live criteria
    MIN_TRADES_PAPER = 50
    MIN_DAYS_PAPER = 3
    MIN_WIN_RATE_PAPER = 0.50
    MIN_SHARPE_PAPER = 0.5  # Risk-adjusted threshold
    MAX_DRAWDOWN_PAPER = 0.20

    def _check_paper_criteria_from_health(
        self, exp: ExperimentRecord, health: dict
    ) -> tuple[bool, list[str]]:
        """Evaluate paper→live promotion using current health metrics."""
        reasons = []
        trades = health.get("total_trades", 0)
        win_rate = health.get("win_rate", 0.0)
        sharpe = health.get("sharpe", 0.0)
        max_dd = health.get("max_drawdown", 0.0)

        if trades < self.MIN_TRADES_PAPER:
            reasons.append(f"trades {trades} < {self.MIN_TRADES_PAPER}")
        if win_rate < self.MIN_WIN_RATE_PAPER:
            reasons.append(f"win_rate {win_rate:.1%} < {self.MIN_WIN_RATE_PAPER:.1%}")
        if sharpe < self.MIN_SHARPE_PAPER:
            reasons.append(f"sharpe {sharpe:.2f} < {self.MIN_SHARPE_PAPER:.2f}")
        if max_dd > self.MAX_DRAWDOWN_PAPER:
            reasons.append(f"dd {max_dd:.1%} > {self.MAX_DRAWDOWN_PAPER:.1%}")

        # Age check (paper running time)
        ref_time = exp.promoted_at or exp.created_at
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - ref_time).days
        if age_days < self.MIN_DAYS_PAPER:
            reasons.append(f"paper age {age_days}d < {self.MIN_DAYS_PAPER}d")

        return (len(reasons) == 0, reasons)

    # Kill thresholds (applied to any mode)
    KILL_WIN_RATE = 0.05
    KILL_SHARPE = -2.0
    KILL_DRAWDOWN = 0.50
    MIN_WARMUP_TRADES = 30

    def __init__(self, runner: Optional[ExperimentRunner] = None):
        self.runner = runner or ExperimentRunner()
        self._last_run: Optional[datetime] = None

    async def run_once(self) -> dict[str, int]:
        """Evaluate all experiments and apply promotion/retirement actions.

        Returns stats: {promoted_shadow→paper, promoted_paper→live, retired, errors}
        """
        stats = {"shadow_to_paper": 0, "paper_to_live": 0, "retired": 0, "errors": 0}
        db = SessionLocal()
        try:
            health_mon = StrategyHealthMonitor()
            # 1. Promote DRAFT → SHADOW (no criteria, just create)
            drafts = (
                db.query(ExperimentRecord)
                .filter_by(status=ExperimentStatus.DRAFT.value)
                .all()
            )
            for exp in drafts:
                exp.status = ExperimentStatus.SHADOW.value
                exp.shadow_trades = 0
                exp.shadow_win_rate = 0.0
                exp.shadow_pnl = 0.0
                exp.created_at = datetime.now(timezone.utc)
                db.add(exp)
                logger.info(f"[AutonomousPromoter] Draft '{exp.name}' → SHADOW (initialized)")
            if drafts:
                db.commit()

            # 2. Evaluate SHADOW → PAPER
            shadows = (
                db.query(ExperimentRecord)
                .filter_by(status=ExperimentStatus.SHADOW.value)
                .all()
            )
            for exp in shadows:
                meets, reasons = self._check_shadow_criteria(exp)
                if meets:
                    exp.status = ExperimentStatus.PAPER.value
                    exp.promoted_at = datetime.now(timezone.utc)
                    db.add(exp)
                    logger.info(
                        f"[AutonomousPromoter] SHADOW→PAPER '{exp.name}': "
                        f"trades={exp.shadow_trades}, wr={exp.shadow_win_rate:.1%}"
                    )
                    stats["shadow_to_paper"] += 1
                else:
                    # If too old and not meeting criteria, retire
                    created_at = exp.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - created_at).days
                    if age_days > self.MIN_DAYS_SHADOW * 2:
                        exp.status = ExperimentStatus.RETIRED.value
                        exp.retired_at = datetime.now(timezone.utc)
                        db.add(exp)
                        logger.warning(
                            f"[AutonomousPromoter] RETIRED '{exp.name}' (shadow, age={age_days}d): "
                            f"{'; '.join(reasons)}"
                        )
                        stats["retired"] += 1
            if shadows:
                db.commit()

            # 3. Evaluate PAPER promotions + kills
            papers = (
                db.query(ExperimentRecord)
                .filter_by(status=ExperimentStatus.PAPER.value)
                .all()
            )
            for exp in papers:
                # 3a. Health-based kill check first
                health = health_mon.assess(exp.name, db)
                if health.get("status") == "killed":
                    exp.status = ExperimentStatus.RETIRED.value
                    exp.retired_at = datetime.now(timezone.utc)
                    db.add(exp)
                    logger.warning(
                        f"[AutonomousPromoter] RETIRED (kill) '{exp.name}': "
                        f"wr={health.get('win_rate', 0):.1%}, "
                        f"sharpe={health.get('sharpe', 0):.2f}, "
                        f"dd={health.get('max_drawdown', 0):.1%}"
                    )
                    stats["retired"] += 1
                    continue  # skip promotion evaluation

                # 3b. Promotion eligibility check using real metrics
                meets, reasons = self._check_paper_criteria_from_health(exp, health)
                if meets:
                    if not settings.AGI_AUTO_PROMOTE:
                        logger.info(
                            f"[AutonomousPromoter] PAPER→LIVE SKIPPED '{exp.name}': "
                            f"AGI_AUTO_PROMOTE=false (manual intervention required)"
                        )
                        continue

                    # Promote to live
                    exp.status = ExperimentStatus.LIVE_PROMOTED.value
                    exp.promoted_at = datetime.now(timezone.utc)
                    db.add(exp)

                    # Auto-enable in StrategyConfig if configured
                    if settings.AGI_AUTO_ENABLE:
                        await self._enable_strategy(exp.name, db)

                    logger.info(
                        f"[AutonomousPromoter] PAPER→LIVE '{exp.name}' promoted automatically "
                        f"(trades={health.get('total_trades', 0)}, wr={health.get('win_rate', 0):.1%})"
                    )
                    stats["paper_to_live"] += 1
                else:
                    # If too old and not meeting criteria, retire
                    ref_time = exp.promoted_at or exp.created_at
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - ref_time).days
                    if age_days > self.MIN_DAYS_PAPER * 3:
                        exp.status = ExperimentStatus.RETIRED.value
                        exp.retired_at = datetime.now(timezone.utc)
                        db.add(exp)
                        logger.warning(
                            f"[AutonomousPromoter] RETIRED '{exp.name}' (paper, age={age_days}d): "
                            f"{'; '.join(reasons)}"
                        )
                        stats["retired"] += 1
            if papers:
                db.commit()

            # 4. Evaluate LIVE_PROMOTED experiments for kill/retirement
            lives = (
                db.query(ExperimentRecord)
                .filter_by(status=ExperimentStatus.LIVE_PROMOTED.value)
                .all()
            )
            for exp in lives:
                health = health_mon.assess(exp.name, db)
                if health.get("status") == "killed":
                    exp.status = ExperimentStatus.RETIRED.value
                    exp.retired_at = datetime.now(timezone.utc)
                    db.add(exp)
                    logger.warning(
                        f"[AutonomousPromoter] RETIRED (kill) '{exp.name}' (live): "
                        f"wr={health.get('win_rate', 0):.1%}, "
                        f"sharpe={health.get('sharpe', 0):.2f}, "
                        f"dd={health.get('max_drawdown', 0):.1%}"
                    )
                    stats["retired"] += 1
            if lives:
                db.commit()

            self._last_run = datetime.now(timezone.utc)
            logger.info(
                f"[AutonomousPromoter] Run complete: "
                f"+{stats['shadow_to_paper']} shadow→paper, "
                f"+{stats['paper_to_live']} paper→live, "
                f"retired={stats['retired']}"
            )
            return stats

        except Exception as e:
            logger.error(f"[AutonomousPromoter] Run failed: {e}", exc_info=True)
            stats["errors"] += 1
            return stats
        finally:
            db.close()

    def _check_shadow_criteria(self, exp: ExperimentRecord) -> tuple[bool, list[str]]:
        """Check if experiment meets shadow→paper criteria."""
        reasons = []
        trades = exp.shadow_trades or 0
        win_rate = exp.shadow_win_rate or 0.0

        if trades < self.MIN_TRADES_SHADOW:
            reasons.append(f"trades {trades} < {self.MIN_TRADES_SHADOW}")
        if exp.shadow_win_rate < self.MIN_WIN_RATE_SHADOW:
            reasons.append(f"win_rate {win_rate:.1%} < {self.MIN_WIN_RATE_SHADOW:.1%}")

        # Age check (handle naive/aware)
        created_at = exp.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created_at).days
        if age_days < self.MIN_DAYS_SHADOW:
            reasons.append(f"age {age_days}d < {self.MIN_DAYS_SHADOW}d")

        # TODO: drawdown from shadow outcomes (need outcome table)

        return (len(reasons) == 0, reasons)

    def _check_paper_criteria(self, exp: ExperimentRecord) -> tuple[bool, list[str]]:
        """Check if experiment meets paper→live criteria."""
        reasons = []
        # For now, use same shadow metrics (paper uses its own metrics stored separately)
        # ExperimentRecord doesn't yet have paper_* columns; we'll infer from outcomes once settled
        # For now, assume shadow metrics apply to paper too (stub)
        trades = exp.shadow_trades or 0  # TODO: separate paper_trades field
        win_rate = exp.shadow_win_rate or 0.0

        if trades < self.MIN_TRADES_PAPER:
            reasons.append(f"trades {trades} < {self.MIN_TRADES_PAPER}")
        if win_rate < self.MIN_WIN_RATE_PAPER:
            reasons.append(f"win_rate {win_rate:.1%} < {self.MIN_WIN_RATE_PAPER:.1%}")

        age_days = (datetime.now(timezone.utc) - exp.promoted_at or exp.created_at).days
        if age_days < self.MIN_DAYS_PAPER:
            reasons.append(f"paper age {age_days}d < {self.MIN_DAYS_PAPER}d")

        # TODO: Sharpe ratio from settled trades
        # TODO: Max drawdown from equity curve

        return (len(reasons) == 0, reasons)

    def _get_paper_trades(self, exp: ExperimentRecord) -> int:
        return exp.shadow_trades or 0  # Stub

    def _get_paper_win_rate(self, exp: ExperimentRecord) -> float:
        return exp.shadow_win_rate or 0.0  # Stub

    def _should_kill(self, exp: ExperimentRecord) -> bool:
        """Return True if experiment is catastrophically bad and should be retired."""
        trades = exp.shadow_trades or 0
        if trades < self.MIN_WARMUP_TRADES:
            return False
        win_rate = exp.shadow_win_rate or 0.0
        if win_rate < self.KILL_WIN_RATE:
            return True
        # Additional kill checks would require outcome metrics (sharpe, drawdown)
        return False

    async def _enable_strategy(self, strategy_name: str, db: Session) -> None:
        """Create/enable StrategyConfig for the promoted experiment and schedule it."""
        from backend.core.scheduler import schedule_strategy  # Lazy to avoid circular import

        config = (
            db.query(StrategyConfig)
            .filter_by(strategy_name=strategy_name)
            .first()
        )
        if config:
            config.enabled = True
            config.updated_at = datetime.now(timezone.utc)
            interval = config.interval_seconds or 60
            logger.info(f"[AutonomousPromoter] Enabled existing StrategyConfig '{strategy_name}' (interval={interval}s)")
        else:
            # Infer interval from strategy registry
            from backend.strategies.registry import STRATEGY_REGISTRY
            strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
            default_interval = 60
            if strategy_cls and hasattr(strategy_cls, "default_interval"):
                default_interval = getattr(strategy_cls, "default_interval", 60)
            config = StrategyConfig(
                strategy_name=strategy_name,
                enabled=True,
                interval_seconds=default_interval,
                mode="live",
            )
            db.add(config)
            interval = default_interval
            logger.info(f"[AutonomousPromoter] Created & enabled StrategyConfig '{strategy_name}' (interval={interval}s)")
        db.commit()

        # Dynamic scheduling so it starts immediately without restart
        try:
            schedule_strategy(strategy_name, interval, mode="live")
        except Exception as e:
            logger.warning(f"[AutonomousPromoter] Failed to dynamically schedule '{strategy_name}': {e}")


# Module-level singleton
autonomous_promoter = AutonomousPromoter()


async def autonomous_promotion_job() -> None:
    """Scheduled job entrypoint for APScheduler."""
    try:
        stats = await autonomous_promoter.run_once()
        logger.info(f"[autonomous_promotion_job] Completed: {stats}")
    except Exception as e:
        logger.error(f"[autonomous_promotion_job] Fatal error: {e}", exc_info=True)
