"""Centralized error logging with structured context and aggregation."""

import logging
import traceback
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import asyncio

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

logger = logging.getLogger(__name__)


@dataclass
class ErrorContext:
    """Structured error context for logging."""
    timestamp: datetime
    error_type: str
    message: str
    endpoint: Optional[str] = None
    method: Optional[str] = None
    user_id: Optional[str] = None
    stack_trace: Optional[str] = None
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with ISO-formatted timestamp."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class ErrorLogger:
    """Centralized error logging with database persistence and aggregation."""

    def __init__(self, db_session: Optional[Session] = None):
        """Initialize error logger with optional database session."""
        self.db_session = db_session
        self._error_buffer = []
        self._error_counts = defaultdict(int)
        self._last_minute_errors = deque(maxlen=60)  # Track last 60 seconds
        self._lock = asyncio.Lock()

    async def log_error(
        self,
        error: Exception,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log error with full context: timestamp, user, endpoint, stack trace."""
        async with self._lock:
            context = ErrorContext(
                timestamp=datetime.now(timezone.utc),
                error_type=type(error).__name__,
                message=str(error),
                endpoint=endpoint,
                method=method,
                user_id=user_id,
                stack_trace=traceback.format_exc(),
                request_id=request_id,
                details=details or {},
            )

            logger.error(
                f"Error in {endpoint or 'unknown'}: {context.error_type} - {context.message}",
                extra={
                    "error_type": context.error_type,
                    "endpoint": endpoint,
                    "request_id": request_id,
                    "user_id": user_id,
                },
                exc_info=error,
            )

            if self.db_session:
                try:
                    await self._persist_error(context)
                except Exception as e:
                    logger.warning(f"Failed to persist error to database: {e}")

            self._error_counts[context.error_type] += 1
            self._last_minute_errors.append(context.timestamp)

    async def _persist_error(self, context: ErrorContext) -> None:
        """Persist error to database."""
        from backend.models.database import ErrorLog

        error_log = ErrorLog(
            timestamp=context.timestamp,
            error_type=context.error_type,
            message=context.message,
            endpoint=context.endpoint,
            method=context.method,
            user_id=context.user_id,
            stack_trace=context.stack_trace,
            status_code=context.status_code,
            request_id=context.request_id,
            details=json.dumps(context.details) if context.details else None,
        )
        self.db_session.add(error_log)
        self.db_session.commit()

    async def get_error_rate(self) -> float:
        """Get error rate in errors per minute."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            one_minute_ago = now - timedelta(minutes=1)

            recent_errors = sum(
                1 for ts in self._last_minute_errors if ts >= one_minute_ago
            )
            return float(recent_errors)

    async def get_error_aggregation(
        self, limit: int = 100
    ) -> Dict[str, Dict[str, Any]]:
        """Get error aggregation by type and endpoint."""
        if not self.db_session:
            return {}

        from backend.models.database import ErrorLog

        try:
            type_counts = (
                self.db_session.query(
                    ErrorLog.error_type, func.count(ErrorLog.id).label("count")
                )
                .group_by(ErrorLog.error_type)
                .order_by(desc("count"))
                .limit(limit)
                .all()
            )

            endpoint_counts = (
                self.db_session.query(
                    ErrorLog.endpoint, func.count(ErrorLog.id).label("count")
                )
                .filter(ErrorLog.endpoint.isnot(None))
                .group_by(ErrorLog.endpoint)
                .order_by(desc("count"))
                .limit(limit)
                .all()
            )

            return {
                "by_type": {error_type: count for error_type, count in type_counts},
                "by_endpoint": {
                    endpoint: count for endpoint, count in endpoint_counts
                },
            }
        except Exception as e:
            logger.error(f"Failed to get error aggregation: {e}")
            return {}

    async def get_recent_errors(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent errors from database (last N errors)."""
        if not self.db_session:
            return []

        from backend.models.database import ErrorLog

        try:
            errors = (
                self.db_session.query(ErrorLog)
                .order_by(desc(ErrorLog.timestamp))
                .limit(limit)
                .all()
            )

            return [
                {
                    "id": error.id,
                    "timestamp": error.timestamp.isoformat(),
                    "error_type": error.error_type,
                    "message": error.message,
                    "endpoint": error.endpoint,
                    "method": error.method,
                    "user_id": error.user_id,
                    "status_code": error.status_code,
                    "request_id": error.request_id,
                    "details": json.loads(error.details) if error.details else None,
                }
                for error in errors
            ]
        except Exception as e:
            logger.error(f"Failed to get recent errors: {e}")
            return []

    async def cleanup_old_errors(self, days: int = 30) -> int:
        """Delete errors older than specified days (default 30 days)."""
        if not self.db_session:
            return 0

        from backend.models.database import ErrorLog

        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            deleted = (
                self.db_session.query(ErrorLog)
                .filter(ErrorLog.timestamp < cutoff_date)
                .delete()
            )
            self.db_session.commit()
            logger.info(f"Deleted {deleted} errors older than {days} days")
            return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup old errors: {e}")
            self.db_session.rollback()
            return 0


def get_error_logger(db_session: Optional[Session] = None) -> ErrorLogger:
    """Get or create global error logger instance."""
    global _error_logger
    if _error_logger is None:
        _error_logger = ErrorLogger(db_session)
    elif db_session and _error_logger.db_session is None:
        _error_logger.db_session = db_session
    return _error_logger


_error_logger: Optional[ErrorLogger] = None
