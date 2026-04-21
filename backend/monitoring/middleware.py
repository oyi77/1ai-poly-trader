"""Middleware for automatic metrics collection."""

from time import perf_counter
from fastapi import Request
import logging

from backend.monitoring import record_api_latency, increment_api_errors
from backend.monitoring.performance_tracker import get_performance_tracker
from backend.models.database import SessionLocal

logger = logging.getLogger("trading_bot")


async def metrics_middleware(request: Request, call_next):
    """
    Middleware to track API request latency and errors.
    
    Automatically records:
    - Request duration (for latency monitoring)
    - Error counts (4xx and 5xx responses)
    - Detailed performance metrics with percentiles
    """
    start_time = perf_counter()
    error_message = None
    
    try:
        response = await call_next(request)
        
        # Record latency in milliseconds
        duration_ms = (perf_counter() - start_time) * 1000
        record_api_latency(duration_ms)
        
        # Track detailed performance metrics
        tracker = get_performance_tracker()
        db = SessionLocal()
        try:
            user_agent = request.headers.get("user-agent")
            tracker.track_request(
                duration_ms=duration_ms,
                endpoint=request.url.path,
                method=request.method,
                status_code=response.status_code,
                db=db,
                user_agent=user_agent
            )
            
            # Periodic cleanup of old metrics
            tracker.maybe_cleanup(db)
        finally:
            db.close()
        
        # Track errors
        if response.status_code >= 400:
            increment_api_errors()
            logger.warning(f"API error: {request.method} {request.url.path} -> {response.status_code}")
        
        return response
        
    except Exception as e:
        # Record failed requests
        duration_ms = (perf_counter() - start_time) * 1000
        record_api_latency(duration_ms)
        increment_api_errors()
        error_message = str(e)
        
        # Track error in performance metrics
        tracker = get_performance_tracker()
        db = SessionLocal()
        try:
            tracker.track_request(
                duration_ms=duration_ms,
                endpoint=request.url.path,
                method=request.method,
                status_code=500,
                db=db,
                error_message=error_message
            )
        finally:
            db.close()
        
        logger.error(f"API exception: {request.method} {request.url.path} -> {error_message}")
        raise
