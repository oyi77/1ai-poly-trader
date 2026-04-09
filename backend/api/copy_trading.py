"""Copy trading routes - leaderboard, signals, positions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import get_db, Signal, SessionLocal, CopyTraderEntry
import logging

logger = logging.getLogger("trading_bot")
router = APIRouter(tags=["copy_trading"])


class ScoredTraderResponse(BaseModel):
    wallet: str
    pseudonym: str
    profit_30d: float
    win_rate: float
    total_trades: int
    unique_markets: int
    estimated_bankroll: float
    score: float
    market_diversity: float


class CopySignalResponse(BaseModel):
    source_wallet: str
    our_side: str
    our_outcome: str
    our_size: float
    market_price: float
    trader_score: float
    reasoning: str
    condition_id: str
    title: str
    timestamp: str


@router.get("/api/copy/leaderboard", response_model=List[ScoredTraderResponse])
async def get_copy_leaderboard(limit: int = 50):
    """Return REAL top-scored traders scraped from Polymarket leaderboard."""
    try:
        from backend.data.polymarket_scraper import fetch_real_leaderboard

        traders = await fetch_real_leaderboard(limit=limit)

        if not traders:
            logger.warning("No real leaderboard data available from Polymarket")
            return []

        result = [
            ScoredTraderResponse(
                wallet=t["wallet"],
                pseudonym=t["pseudonym"],
                profit_30d=round(t["profit_30d"], 2),
                win_rate=round(t["win_rate"], 3),
                total_trades=t["total_trades"],
                unique_markets=t["unique_markets"],
                estimated_bankroll=round(t["estimated_bankroll"], 2),
                score=round(t["score"], 3),
                market_diversity=round(t["market_diversity"], 3),
            )
            for t in traders
        ]

        logger.info(f"Returning {len(result)} real traders from Polymarket leaderboard")
        return result

    except Exception as e:
        logger.error(f"Error fetching real leaderboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch real leaderboard: {str(e)}")


@router.get("/api/copy/signals", response_model=List[CopySignalResponse])
async def get_copy_signals(limit: int = 20):
    """Return recent copy trade signals from the DB."""
    try:
        db = SessionLocal()
        signals = (
            db.query(Signal)
            .filter(Signal.market_type == "copy")
            .order_by(Signal.timestamp.desc())
            .limit(limit)
            .all()
        )
        db.close()
        return [
            CopySignalResponse(
                source_wallet=s.sources[0] if s.sources else "",
                our_side=s.direction,
                our_outcome="YES",
                our_size=s.suggested_size,
                market_price=s.market_price,
                trader_score=s.confidence * 100,
                reasoning=s.reasoning,
                condition_id=s.market_ticker,
                title=s.market_ticker,
                timestamp=s.timestamp.isoformat(),
            )
            for s in signals
        ]
    except Exception:
        return []


@router.get("/api/copy-trader/positions")
async def get_copy_trader_positions(db: Session = Depends(get_db)):
    """Return recent copy trader position entries from DB."""
    entries = (
        db.query(CopyTraderEntry)
        .order_by(CopyTraderEntry.opened_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "wallet": e.wallet,
            "condition_id": e.condition_id,
            "side": e.side,
            "size": e.size,
            "opened_at": e.opened_at.isoformat() if e.opened_at else None,
        }
        for e in entries
    ]


@router.get("/api/copy-trader/status")
async def get_copy_trader_status(db: Session = Depends(get_db)):
    """Return copy trader status including tracked wallets and recent signals."""
    try:
        wallet_entries = db.query(
            CopyTraderEntry.wallet,
            func.count(CopyTraderEntry.id).label('trades'),
            func.sum(CopyTraderEntry.pnl).label('pnl')
        ).group_by(CopyTraderEntry.wallet).all()

        wallet_details = []
        for addr, trades, pnl in wallet_entries:
            pseudonym = addr[:8] + "..."
            signal = db.query(Signal).filter(
                Signal.market_type == "copy",
                Signal.sources.contains([addr])
            ).first()
            if signal and signal.sources and len(signal.sources) > 1:
                pseudonym = signal.sources[1] if len(signal.sources) > 1 else pseudonym

            score = min(100, (trades * 2) + (pnl if pnl > 0 else 0))
            wallet_details.append({
                "address": addr,
                "pseudonym": pseudonym,
                "score": score,
                "profit_30d": pnl or 0.0
            })

        recent_signals = db.query(Signal).filter(
            Signal.market_type == "copy"
        ).order_by(Signal.timestamp.desc()).limit(10).all()

        signals_data = [
            {
                "market_ticker": s.market_ticker,
                "direction": s.direction,
                "edge": s.edge,
                "confidence": s.confidence,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None
            }
            for s in recent_signals
        ]

        return {
            "enabled": len(wallet_details) > 0,
            "tracked_wallets": len(wallet_details),
            "wallet_details": wallet_details,
            "recent_signals": signals_data,
            "status": "active" if len(wallet_details) > 0 else "idle",
            "errors": []
        }
    except Exception as e:
        logger.error(f"Error getting copy trader status: {e}")
        return {
            "enabled": False,
            "tracked_wallets": 0,
            "wallet_details": [],
            "recent_signals": [],
            "status": "error",
            "errors": [{"source": "database", "message": str(e)}]
        }
