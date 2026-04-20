"""Activity log API endpoints."""

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, ActivityLog
from backend.core.activity_logger import activity_logger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activities", tags=["activities"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
async def get_activities(
    limit: int = Query(100, ge=1, le=1000),
    strategy: Optional[str] = Query(None),
    decision_type: Optional[str] = Query(None),
    days: Optional[int] = Query(None, ge=1),
    confidence_min: Optional[float] = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db)
):
    """
    Get activity logs with optional filtering.
    
    Query parameters:
    - limit: Maximum records to return (1-1000, default 100)
    - strategy: Filter by strategy name (e.g., 'btc_momentum')
    - decision_type: Filter by decision type ('entry', 'exit', 'hold', 'adjustment')
    - days: Filter to last N days
    - confidence_min: Minimum confidence score (0.0-1.0)
    """
    try:
        query = db.query(ActivityLog)
        
        if strategy:
            query = query.filter(ActivityLog.strategy_name == strategy)
        
        if decision_type:
            query = query.filter(ActivityLog.decision_type == decision_type)
        
        if days:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(ActivityLog.timestamp >= cutoff)
        
        if confidence_min is not None:
            query = query.filter(ActivityLog.confidence_score >= confidence_min)
        
        query = query.order_by(ActivityLog.timestamp.desc()).limit(limit)
        
        activities = query.all()
        
        result = []
        for activity in activities:
            result.append({
                "id": activity.id,
                "timestamp": activity.timestamp.isoformat(),
                "strategy_name": activity.strategy_name,
                "decision_type": activity.decision_type,
                "data": activity.data,
                "confidence_score": activity.confidence_score,
                "mode": activity.mode
            })
        
        return {
            "activities": result,
            "count": len(result),
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Failed to retrieve activities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{activity_id}")
async def get_activity_by_id(
    activity_id: int,
    db: Session = Depends(get_db)
):
    """Get a single activity log by ID."""
    try:
        activity = db.query(ActivityLog).filter(ActivityLog.id == activity_id).first()
        
        if not activity:
            raise HTTPException(status_code=404, detail=f"Activity {activity_id} not found")
        
        return {
            "id": activity.id,
            "timestamp": activity.timestamp.isoformat(),
            "strategy_name": activity.strategy_name,
            "decision_type": activity.decision_type,
            "data": activity.data,
            "confidence_score": activity.confidence_score,
            "mode": activity.mode
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve activity {activity_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
