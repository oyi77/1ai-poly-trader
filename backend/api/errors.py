"""Frontend error reporting endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

from backend.models.database import get_db

logger = logging.getLogger("trading_bot")

router = APIRouter(prefix="/api/errors", tags=["errors"])


class FrontendErrorReport(BaseModel):
    message: str
    stack: str | None = None
    componentStack: str | None = None
    timestamp: str
    userAgent: str


@router.post("/frontend")
async def report_frontend_error(
    error_report: FrontendErrorReport,
    db: Session = Depends(get_db),
):
    """
    Receive and log frontend errors from ErrorBoundary.
    
    Args:
        error_report: Error details from frontend
        db: Database session
    
    Returns:
        Confirmation of error receipt
    """
    try:
        logger.error(
            f"Frontend Error: {error_report.message}",
            extra={
                "stack": error_report.stack,
                "componentStack": error_report.componentStack,
                "userAgent": error_report.userAgent,
                "timestamp": error_report.timestamp,
            },
        )
        
        return {
            "status": "received",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Failed to process frontend error report: {e}")
        return {
            "status": "error",
            "message": "Failed to process error report",
        }
