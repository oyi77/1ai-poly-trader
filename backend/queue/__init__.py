"""
PolyEdge job queue system.

Provides abstract interfaces for queue and cache operations with pluggable
backends (SQLite for Phase 1, Redis for Phase 2).

Usage:
    from backend.queue import create_queue, create_cache

    queue = create_queue()
    cache = create_cache()

    # Enqueue a job
    job_id = queue.enqueue(
        job_type="market_scan",
        payload={"markets": ["BTC-5min"]},
        priority="high"
    )

    # Check cache for idempotency
    if not cache.exists(f"job:{job_id}"):
        # Process job...
        cache.set(f"job:{job_id}", True, ttl_seconds=300)
"""

from backend.queue.abstract import (
    AbstractQueue,
    AbstractCache,
    Job,
    create_queue,
    create_cache,
)
from backend.queue.handlers import (
    market_scan,
    settlement_check,
    signal_generation,
    weather_scan,
)
from backend.queue.worker import Worker

__all__ = [
    "AbstractQueue",
    "AbstractCache",
    "Job",
    "create_queue",
    "create_cache",
    "market_scan",
    "settlement_check",
    "signal_generation",
    "weather_scan",
    "Worker",
]
