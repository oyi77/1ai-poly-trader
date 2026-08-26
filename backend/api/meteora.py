"""Meteora DLMM REST endpoints: on-demand screening + candidate history."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.api.auth import require_admin_from_cookie, require_csrf
from backend.data.meteora.service import run_screening_cycle
from backend.models.database import get_db
from backend.models.meteora_db import MeteoraCandidate

# require_admin_from_cookie accepts BOTH Bearer (tests/scripts) and the
# browser cookie+CSRF session — matching the React admin auth flow.
router = APIRouter(
    prefix="/meteora",
    tags=["meteora"],
    dependencies=[Depends(require_admin_from_cookie)],
)


@router.post("/screen")
async def screen_now(
    timeframe: str = Query("30m"),
    category: str = Query("trending"),
    page_size: int = Query(100, ge=1, le=500),
    persist: bool = Query(True),
) -> dict[str, Any]:
    """Run one screening cycle immediately and return its summary."""
    try:
        return await run_screening_cycle(
            timeframe=timeframe,
            category=category,
            page_size=page_size,
            persist=persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/candidates")
def latest_candidates(
    limit: int = Query(25, ge=1, le=200),
    include_rejected: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Most recent screening candidates, newest cycle first."""
    q = db.query(MeteoraCandidate)
    if not include_rejected:
        q = q.filter(MeteoraCandidate.rejected.is_(False))
    rows = (
        q.order_by(desc(MeteoraCandidate.created_at), desc(MeteoraCandidate.degen_score))
        .limit(limit)
        .all()
    )
    return [
        {
            "cycle_id": r.cycle_id,
            "pool_address": r.pool_address,
            "name": r.name,
            "degen_score": r.degen_score,
            "weighted_score": r.weighted_score,
            "subscores": {
                "trading": r.sub_trading,
                "lp": r.sub_lp,
                "fees": r.sub_fees,
                "liquidity": r.sub_liquidity,
            },
            "rejected": bool(r.rejected),
            "reject_reason": r.reject_reason,
            "signal_snapshot": r.signal_snapshot,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/candidates/{cycle_id}")
def candidates_for_cycle(
    cycle_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (
        db.query(MeteoraCandidate)
        .filter(MeteoraCandidate.cycle_id == cycle_id)
        .order_by(desc(MeteoraCandidate.degen_score))
        .limit(limit)
        .all()
    )
    return [
        {
            "pool_address": r.pool_address,
            "name": r.name,
            "degen_score": r.degen_score,
            "rejected": bool(r.rejected),
            "reject_reason": r.reject_reason,
        }
        for r in rows
    ]


@router.get("/cycles/latest", response_model=dict[str, Any] | None)
def latest_cycle_summary(db: Session = Depends(get_db)) -> dict[str, Any] | None:
    """Aggregate counts for the most recent persisted cycle."""
    latest = (
        db.query(MeteoraCandidate.cycle_id)
        .order_by(desc(MeteoraCandidate.created_at))
        .first()
    )
    if not latest:
        return None
    cycle_id = latest[0]
    rows = db.query(MeteoraCandidate).filter(MeteoraCandidate.cycle_id == cycle_id).all()
    accepted = [r for r in rows if not r.rejected]
    return {
        "cycle_id": cycle_id,
        "screened": len(rows),
        "accepted": len(accepted),
        "rejected": len(rows) - len(accepted),
        "top": sorted(
            (
                {
                    "pool_address": r.pool_address,
                    "name": r.name,
                    "degen_score": r.degen_score,
                }
                for r in accepted
            ),
            key=lambda x: x["degen_score"],
            reverse=True,
        )[:10],
    }
