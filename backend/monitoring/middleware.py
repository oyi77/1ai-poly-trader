"""Middleware for automatic metrics collection."""

from time import perf_counter
from fastapi import Request
import logging

from backend.monitoring import record_api_latency, increment_api_errors

logger = logging.getLogger("trading_bot")


async def metrics_middleware(request: Request, call_next):
    """
    Middleware to track API request latency and errors.
    
    Automatically records:
    - Request duration (for latency monitoring)
    - Error counts (4xx and 5xx responses)
    """
    start_time = perf_counter()
    
    try:
        response = await call_next(request)
        
        # Record latency in milliseconds
        duration_ms = (perf_counter() - start_time) * 1000
        record_api_latency(duration_ms)
        
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
        
        logger.error(f"API exception: {request.method} {request.url.path} -> {str(e)}")
        raise
