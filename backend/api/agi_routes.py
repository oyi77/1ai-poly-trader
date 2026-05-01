from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.security import HTTPBasicCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.models.database import get_db, Base, engine
from backend.core.agi_orchestrator import AGIOrchestrator, AGIStatus
from backend.core.agi_goal_engine import AGIGoalEngine
from backend.core.strategy_composer import StrategyComposer, ComposedStrategy
from backend.core.knowledge_graph import KnowledgeGraph
from backend.models.kg_models import DecisionAuditLog, ExperimentRecord, KGEntity as KGEntityModel, KGRelation as KGRelationModel

router = APIRouter(tags=["AGI"])


@router.get("/regime")
async def get_regime(db: Session = Depends(get_db)):
    from backend.core.regime_detector import RegimeDetector
    detector = RegimeDetector()
    result = detector.detect_regime({})
    return {"regime": result.regime.value, "confidence": result.confidence}


@router.get("/goal")
async def get_goal(db: Session = Depends(get_db)):
    engine = AGIGoalEngine(session=db)
    regime = None
    try:
        from backend.core.regime_detector import RegimeDetector
        detector = RegimeDetector()
        regime = detector.detect_regime(market_data={}).regime
    except Exception:
        pass
    goal = engine.get_current_goal(regime or None)
    return {"goal": goal.value, "reason": engine._goal_reason}


@router.get("/decisions")
async def get_decisions(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * page_size
    query = db.query(DecisionAuditLog).order_by(DecisionAuditLog.timestamp.desc())
    total = query.count()
    records = query.offset(offset).limit(page_size).all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "decisions": [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "decision_type": r.decision_type,
                "input_data": r.input_data,
                "output_data": r.output_data,
                "reasoning": r.reasoning,
            }
            for r in records
        ],
    }


@router.get("/strategies/composed")
async def list_composed_strategies(db: Session = Depends(get_db)):
    records = db.query(ExperimentRecord).all()
    return {
        "strategies": [
            {
                "id": str(r.id),
                "name": r.name,
                "status": r.status,
                "blocks": r.strategy_composition.get("blocks", []) if r.strategy_composition else [],
                "shadow_pnl": r.shadow_pnl,
                "shadow_trades": r.shadow_trades,
                "shadow_win_rate": r.shadow_win_rate,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }


@router.post("/strategies/compose")
async def compose_strategy(
    name: str = Body(...),
    blocks: list[dict[str, str]] = Body(...),
    db: Session = Depends(get_db),
):
    from backend.core.agi_types import StrategyBlock
    composer = StrategyComposer(session=db)
    block_objs = [StrategyBlock(**b) for b in blocks]
    composed = composer.compose(block_objs, name=name)
    validation = composer.validate_composition(composed)
    if not validation:
        raise HTTPException(status_code=400, detail={"errors": validation.errors})
    experiment_id = composer.register_composed(composed)
    return {"id": experiment_id, "name": composed.name, "status": composed.status}


@router.get("/experiments")
async def list_experiments(db: Session = Depends(get_db)):
    records = db.query(ExperimentRecord).all()
    return {
        "experiments": [
            {
                "id": str(r.id),
                "name": r.name,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "promoted_at": r.promoted_at.isoformat() if r.promoted_at else None,
            }
            for r in records
        ]
    }


@router.get("/knowledge-graph")
async def query_kg(
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    kg = KnowledgeGraph(session=db)
    query = db.query(KGEntityModel)
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    entities = query.all()
    return {
        "entities": [
            {
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "properties": e.properties,
            }
            for e in entities
        ]
    }


@router.post("/emergency-stop")
async def emergency_stop(db: Session = Depends(get_db)):
    orchestrator = AGIOrchestrator(session=db)
    orchestrator.emergency_stop()
    return {"status": "stopped", "message": "AGI emergency stop activated"}


@router.get("/status")
async def get_status(db: Session = Depends(get_db)):
    orchestrator = AGIOrchestrator(session=db)
    status = orchestrator.get_status()
    return status.to_dict()


@router.post("/run-cycle")
async def run_cycle(db: Session = Depends(get_db)):
    orchestrator = AGIOrchestrator(session=db)
    result = await orchestrator.run_cycle()
    return result.to_dict()


@router.post("/goal/override")
async def override_goal(
    goal: str = Body(...),
    reason: str = Body(...),
    db: Session = Depends(get_db),
):
    from backend.core.agi_types import AGIGoal
    try:
        goal_enum = AGIGoal(goal)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid goal: {goal}")
    engine = AGIGoalEngine(session=db)
    audit = engine.set_goal(goal_enum, reason)
    return {"goal": goal, "reason": reason, "timestamp": audit.timestamp.isoformat()}
