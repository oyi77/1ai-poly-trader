"""API endpoints for strategy proposal management."""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db, StrategyProposal as DBProposal, Trade
from backend.api.auth import require_admin
from backend.ai.proposal_generator import ProposalGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


class ProposalResponse(BaseModel):
    id: int
    strategy_name: str
    change_details: dict
    expected_impact: str
    admin_decision: str
    created_at: str
    executed_at: Optional[str] = None


class ApprovalRequest(BaseModel):
    admin_user_id: str


@router.get("", response_model=List[ProposalResponse])
async def list_proposals(
    status: Optional[str] = "pending",
    db: Session = Depends(get_db)
):
    """List strategy proposals filtered by status.
    
    Query params:
        status: Filter by admin_decision status (pending, approved, rejected)
    """
    query = db.query(DBProposal)
    
    if status:
        query = query.filter(DBProposal.admin_decision == status)
    
    proposals = query.order_by(DBProposal.created_at.desc()).all()
    
    return [
        ProposalResponse(
            id=p.id,
            strategy_name=p.strategy_name,
            change_details=p.change_details,
            expected_impact=p.expected_impact,
            admin_decision=p.admin_decision,
            created_at=p.created_at.isoformat() if p.created_at else "",
            executed_at=p.executed_at.isoformat() if p.executed_at else None
        )
        for p in proposals
    ]


@router.post("/{proposal_id}/approve", status_code=status.HTTP_200_OK)
async def approve_proposal(
    proposal_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin)
):
    """Approve a strategy proposal (admin only).
    
    Requires admin authentication. Returns 403 if called by non-admin.
    """
    generator = ProposalGenerator()
    
    success = generator.approve_proposal(proposal_id, request.admin_user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal {proposal_id} not found or already processed"
        )
    
    return {"status": "approved", "proposal_id": proposal_id}


@router.post("/{proposal_id}/reject", status_code=status.HTTP_200_OK)
async def reject_proposal(
    proposal_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin)
):
    """Reject a strategy proposal (admin only).
    
    Requires admin authentication. Returns 403 if called by non-admin.
    """
    generator = ProposalGenerator()
    
    success = generator.reject_proposal(proposal_id, request.admin_user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal {proposal_id} not found or already processed"
        )
    
    return {"status": "rejected", "proposal_id": proposal_id}


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_proposal(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin)
):
    """Generate a new strategy proposal from recent trades (admin only).
    
    Analyzes the last 20 trades and uses Claude API to generate improvement proposal.
    """
    recent_trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(20).all()
    
    if not recent_trades:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No trades available for analysis"
        )
    
    generator = ProposalGenerator()
    proposal = await generator.generate_proposal(recent_trades)
    
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate proposal"
        )
    
    return {
        "status": "created",
        "strategy_name": proposal.strategy_name,
        "change_type": proposal.change_type,
        "confidence": proposal.confidence
    }
