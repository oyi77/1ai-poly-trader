from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.core.agi_types import MarketRegime, AGIGoal
from backend.models.kg_models import Base, DecisionAuditLog


class AGIStatus:
    def __init__(
        self,
        regime: MarketRegime,
        goal: AGIGoal,
        allocations: dict[str, float] | None = None,
        health: str = "healthy",
        emergency_stop: bool = False,
    ):
        self.regime = regime
        self.goal = goal
        self.allocations = allocations or {}
        self.health = health
        self.emergency_stop = emergency_stop

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "goal": self.goal.value,
            "allocations": self.allocations,
            "health": self.health,
            "emergency_stop": self.emergency_stop,
        }


class AGICycleResult:
    def __init__(
        self,
        regime: MarketRegime,
        goal: AGIGoal,
        actions_taken: int = 0,
        errors: list[str] | None = None,
    ):
        self.regime = regime
        self.goal = goal
        self.actions_taken = actions_taken
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "goal": self.goal.value,
            "actions_taken": self.actions_taken,
            "errors": self.errors,
        }


class AGIOrchestrator:
    def __init__(self, session: Optional[Session] = None, db_url: str = "sqlite:///:memory:"):
        self._emergency_stop = False
        self._current_regime = None
        self._current_goal = None
        if session is not None:
            self._session = session
            self._owns_session = False
        else:
            self._engine = create_engine(db_url)
            Base.metadata.create_all(self._engine)
            self._session = sessionmaker(bind=self._engine)()
            self._owns_session = True

    def close(self):
        if self._owns_session:
            self._session.close()

    def run_cycle(self) -> AGICycleResult:
        if self._emergency_stop:
            return AGICycleResult(
                regime=MarketRegime.UNKNOWN,
                goal=AGIGoal.PRESERVE_CAPITAL,
                errors=["Emergency stop active"],
            )

        errors = []
        actions = 0

        try:
            from backend.core.regime_detector import RegimeDetector
            detector = RegimeDetector()
            regime = detector.detect_regime(market_data={}).regime
            self._current_regime = regime
            actions += 1
        except Exception as e:
            errors.append(f"Regime detection failed: {e}")
            regime = MarketRegime.UNKNOWN

        try:
            from backend.core.agi_goal_engine import AGIGoalEngine
            goal_engine = AGIGoalEngine(session=self._session)
            goal = goal_engine.get_current_goal(regime)
            self._current_goal = goal
            actions += 1
        except Exception as e:
            errors.append(f"Goal engine failed: {e}")
            goal = AGIGoal.PRESERVE_CAPITAL

        try:
            from backend.core.strategy_allocator import RegimeAwareAllocator
            from backend.core.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(session=self._session)
            allocator = RegimeAwareAllocator(kg=kg)
            allocations = allocator.allocate(["btc_momentum", "weather_emos"], regime, capital=10000.0)
            actions += 1
        except Exception as e:
            errors.append(f"Allocation failed: {e}")
            allocations = {}

        self._log_cycle(regime, goal, allocations, errors)

        return AGICycleResult(
            regime=regime,
            goal=goal,
            actions_taken=actions,
            errors=errors,
        )

    def get_status(self) -> AGIStatus:
        regime = self._current_regime or MarketRegime.UNKNOWN
        goal = self._current_goal or AGIGoal.PRESERVE_CAPITAL
        return AGIStatus(
            regime=regime,
            goal=goal,
            health="stopped" if self._emergency_stop else "healthy",
            emergency_stop=self._emergency_stop,
        )

    def emergency_stop(self) -> None:
        self._emergency_stop = True
        audit = DecisionAuditLog(
            timestamp=datetime.now(timezone.utc),
            agent_name="AGIOrchestrator",
            decision_type="agi_emergency_stop",
            input_data={"action": "emergency_stop"},
            output_data={"status": "stopped"},
            confidence=1.0,
            reasoning="Emergency stop activated",
        )
        self._session.add(audit)
        self._session.commit()

    def _log_cycle(
        self, regime: MarketRegime, goal: AGIGoal, allocations: dict, errors: list[str]
    ):
        audit = DecisionAuditLog(
            timestamp=datetime.now(timezone.utc),
            agent_name="AGIOrchestrator",
            decision_type="agi_cycle",
            input_data={
                "regime": regime.value,
                "goal": goal.value,
                "allocations": allocations,
            },
            output_data={"errors": errors, "actions": len(allocations)},
            confidence=1.0 if not errors else 0.5,
            reasoning=f"AGI cycle completed: regime={regime.value}, goal={goal.value}",
        )
        self._session.add(audit)
        self._session.commit()
