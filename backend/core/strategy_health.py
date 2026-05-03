"""
Strategy Health Monitor — kill-switch, PSI drift detection, warm-up guard.

Called by online_learner after each trade settlement and by scheduler every cycle.
"""
import math
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.models.outcome_tables import StrategyOutcome, StrategyHealthRecord

logger = logging.getLogger(__name__)


class StrategyHealthMonitor:
    MIN_WARMUP_TRADES = 30
    KILL_WIN_RATE = 0.05
    WARN_WIN_RATE = 0.15
    WARN_BRIER = 0.4
    WARN_PSI = 0.25
    KILL_SHARPE = -2.0
    KILL_DRAWDOWN = 0.50

    def assess(self, strategy: str, db: Session, readonly: bool = False) -> Dict[str, Any]:
        """
        Compute full health metrics for a strategy.

        Args:
            strategy: Strategy name to assess.
            db: Database session.
            readonly: If True, compute metrics only — do NOT disable strategies or persist records.

        Returns dict: total_trades, wins, losses, win_rate, sharpe, max_drawdown,
                      brier_score, psi_score, status
        """
        if strategy == "unknown":
            return self._empty_health(strategy, "active")

        outcomes = (
            db.query(StrategyOutcome)
            .filter(StrategyOutcome.strategy == strategy)
            .order_by(StrategyOutcome.settled_at.asc())
            .all()
        )

        if not outcomes:
            outcomes = self._outcomes_from_trades(strategy, db)

        total = len(outcomes)
        wins = sum(1 for o in outcomes if o.result == "win")
        losses = sum(1 for o in outcomes if o.result == "loss")
        win_rate = wins / total if total > 0 else 0.0

        sharpe = self._sharpe_from_outcomes(outcomes)
        max_dd = self._max_drawdown_from_outcomes(outcomes)
        psi = self.compute_psi(strategy, db)
        brier = self._brier_from_outcomes(outcomes)

        # Determine status
        if self._should_kill_metrics(total, win_rate, sharpe, max_dd):
            status = "killed"
            if not readonly:
                self._disable_strategy(strategy, db)
            logger.warning(
                f"[HealthMonitor] Strategy '{strategy}' KILLED — "
                f"win_rate={win_rate:.3f}, sharpe={sharpe:.2f}, drawdown={max_dd:.2f}"
            )
        elif self._should_warn_metrics(win_rate, brier, psi):
            status = "warned"
            logger.warning(
                f"[HealthMonitor] Strategy '{strategy}' WARNED — "
                f"win_rate={win_rate:.3f}, brier={brier:.3f}, psi={psi:.3f}"
            )
        else:
            status = "active"

        health = {
            "strategy": strategy,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "brier_score": brier,
            "psi_score": psi,
            "status": status,
        }

        if not readonly:
            self._persist_health(health, db)
        return health

    def should_kill(self, strategy: str, db: Session) -> bool:
        """True if strategy meets kill criteria (after warm-up)."""
        if strategy == "unknown":
            return False
        outcomes = (
            db.query(StrategyOutcome)
            .filter(StrategyOutcome.strategy == strategy)
            .all()
        )
        total = len(outcomes)
        if total < self.MIN_WARMUP_TRADES:
            return False
        wins = sum(1 for o in outcomes if o.result == "win")
        win_rate = wins / total
        sharpe = self._sharpe_from_outcomes(outcomes)
        max_dd = self._max_drawdown_from_outcomes(outcomes)
        return self._should_kill_metrics(total, win_rate, sharpe, max_dd)

    def should_warn(self, strategy: str, db: Session) -> bool:
        """True if strategy shows warning signs."""
        outcomes = (
            db.query(StrategyOutcome)
            .filter(StrategyOutcome.strategy == strategy)
            .all()
        )
        if not outcomes:
            return False
        total = len(outcomes)
        wins = sum(1 for o in outcomes if o.result == "win")
        win_rate = wins / total if total > 0 else 0.0
        brier = self._brier_from_outcomes(outcomes)
        psi = self.compute_psi(strategy, db)
        return self._should_warn_metrics(win_rate, brier, psi)

    def compute_psi(self, strategy: str, db: Session) -> float:
        """
        Population Stability Index comparing last 30 vs previous 30 outcomes.
        Uses win/loss as 2 bins. Returns 0.0 if insufficient data.
        """
        outcomes = (
            db.query(StrategyOutcome)
            .filter(StrategyOutcome.strategy == strategy)
            .order_by(StrategyOutcome.settled_at.desc())
            .limit(60)
            .all()
        )
        if len(outcomes) < 60:
            return 0.0

        recent = outcomes[:30]
        previous = outcomes[30:60]

        def win_rate(group):
            wins = sum(1 for o in group if o.result == "win")
            return wins / len(group)

        r_win = win_rate(recent)
        p_win = win_rate(previous)

        # Clamp to avoid log(0)
        eps = 1e-6
        r_win = max(eps, min(1 - eps, r_win))
        p_win = max(eps, min(1 - eps, p_win))
        r_loss = 1 - r_win
        p_loss = 1 - p_win

        psi = (r_win - p_win) * math.log(r_win / p_win) + \
              (r_loss - p_loss) * math.log(r_loss / p_loss)
        return abs(psi)

    def compute_sharpe(self, strategy: str, db: Session) -> float:
        """Sharpe ratio from recent trade PnLs. Returns 0.0 if insufficient data."""
        outcomes = (
            db.query(StrategyOutcome)
            .filter(StrategyOutcome.strategy == strategy)
            .order_by(StrategyOutcome.settled_at.desc())
            .limit(100)
            .all()
        )
        return self._sharpe_from_outcomes(outcomes)

    def compute_max_drawdown(self, strategy: str, db: Session) -> float:
        """Peak-to-trough from cumulative PnL. Returns 0.0 if no data."""
        outcomes = (
            db.query(StrategyOutcome)
            .filter(StrategyOutcome.strategy == strategy)
            .order_by(StrategyOutcome.settled_at.asc())
            .all()
        )
        return self._max_drawdown_from_outcomes(outcomes)

    # ── private helpers ──────────────────────────────────────────────────────

    def _should_kill_metrics(self, total: int, win_rate: float, sharpe: float, max_dd: float) -> bool:
        if total < self.MIN_WARMUP_TRADES:
            return False
        if win_rate < self.KILL_WIN_RATE:
            return True
        if sharpe < self.KILL_SHARPE and max_dd > self.KILL_DRAWDOWN:
            return True
        return False

    def _should_warn_metrics(self, win_rate: float, brier: float, psi: float) -> bool:
        return win_rate < self.WARN_WIN_RATE or brier > self.WARN_BRIER or psi > self.WARN_PSI

    def _sharpe_from_outcomes(self, outcomes) -> float:
        pnls = [o.pnl for o in outcomes if o.pnl is not None]
        if len(pnls) < 2:
            return 0.0
        n = len(pnls)
        mean = sum(pnls) / n
        variance = sum((p - mean) ** 2 for p in pnls) / n
        std = math.sqrt(variance) if variance > 0 else 1e-9
        return (mean / std) * math.sqrt(n)

    def _max_drawdown_from_outcomes(self, outcomes) -> float:
        pnls = [o.pnl for o in outcomes if o.pnl is not None]
        if not pnls:
            return 0.0
        peak = 0.0
        equity = 0.0
        max_dd = 0.0
        for p in pnls:
            equity += p
            if equity > peak:
                peak = equity
            dd = (peak - equity) / max(abs(peak), 1e-9)
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _brier_from_outcomes(self, outcomes) -> float:
        pairs = [
            (o.model_probability, 1 if o.result == "win" else 0)
            for o in outcomes
            if o.model_probability is not None and o.result in ("win", "loss")
        ]
        if not pairs:
            return 0.0
        return sum((p - a) ** 2 for p, a in pairs) / len(pairs)

    def _disable_strategy(self, strategy: str, db: Session) -> None:
        """Set strategy_config.enabled = False for the given strategy."""
        try:
            from backend.models.database import StrategyConfig
            config = db.query(StrategyConfig).filter(
                StrategyConfig.strategy_name == strategy
            ).first()
            if config:
                config.enabled = False
                db.commit()
                logger.info(f"[HealthMonitor] Disabled strategy '{strategy}' in config")
            else:
                logger.warning(
                    f"[HealthMonitor] No config row for '{strategy}' — cannot disable"
                )
        except Exception as e:
            logger.error(f"[HealthMonitor] Failed to disable strategy '{strategy}': {e}")
            db.rollback()

    def _persist_health(self, health: Dict[str, Any], db: Session) -> None:
        """Insert a StrategyHealthRecord row."""
        try:
            record = StrategyHealthRecord(
                strategy=health["strategy"],
                total_trades=health["total_trades"],
                wins=health["wins"],
                losses=health["losses"],
                win_rate=health["win_rate"],
                sharpe=health["sharpe"],
                max_drawdown=health["max_drawdown"],
                brier_score=health["brier_score"],
                psi_score=health["psi_score"],
                status=health["status"],
                last_updated=datetime.now(timezone.utc),
            )
            db.add(record)
            db.commit()
        except Exception as e:
            logger.error(f"[HealthMonitor] Failed to persist health record: {e}")
            db.rollback()

    def _empty_health(self, strategy: str, status: str) -> Dict[str, Any]:
        return {
            "strategy": strategy,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "brier_score": 0.0,
            "psi_score": 0.0,
            "status": status,
        }

    def _outcomes_from_trades(self, strategy: str, db: Session) -> list:
        from backend.models.database import Trade
        return (
            db.query(Trade)
            .filter(Trade.strategy == strategy, Trade.settled == 1, Trade.result.in_(["win", "loss"]))
            .order_by(Trade.settlement_time.asc())
            .all()
        )
