"""
arq-based Redis queue implementation.

RQ-015: arq-based Redis queue
"""
import asyncio
import logging
from typing import Optional, Dict, Any

from backend.job_queue.abstract import AbstractQueue, Job

logger = logging.getLogger("trading_bot")

# Priority → arq queue name mapping
_PRIORITY_QUEUE_MAP = {
    "critical": "arq:queue:critical",
    "high": "arq:queue:high",
    "medium": "arq:queue:medium",
    "low": "arq:queue:low",
}


class RedisQueue(AbstractQueue):
    """
    arq-based Redis job queue.

    Enqueueing is done via arq's Redis pool. arq workers consume jobs
    internally — dequeue() is not meaningful in this model.

    complete() and fail() are no-ops because arq tracks job lifecycle
    via JobResult stored in Redis; workers report outcomes automatically.
    """

    def __init__(
        self,
        redis_url: str,
        max_jobs: int = 1,
        job_timeout: int = 300,
    ):
        """
        Args:
            redis_url: Redis connection URL (e.g. "redis://localhost:6379")
            max_jobs: Maximum concurrent jobs (used by arq worker config)
            job_timeout: Job execution timeout in seconds
        """
        self._redis_url = redis_url
        self._max_jobs = max_jobs
        self._job_timeout = job_timeout

    def _get_redis_settings(self):
        """Return arq RedisSettings for the configured URL."""
        from arq.connections import RedisSettings
        return RedisSettings.from_dsn(self._redis_url)

    def _run_async(self, coro):
        """Run an async coroutine synchronously, compatible with Python 3.14."""
        try:
            asyncio.get_running_loop()
            # Already inside a running loop — run in a separate thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(coro)

    def enqueue(
        self,
        job_type: str,
        payload: Dict[str, Any],
        priority: str = "medium",
        idempotency_key: Optional[str] = None,
    ) -> str:
        """
        Enqueue a job into the arq Redis queue.

        Args:
            job_type: Task function name (must match arq WorkerSettings.functions)
            payload: Job data dict passed as first argument to the task function
            priority: One of 'critical', 'high', 'medium', 'low'
            idempotency_key: Optional job ID to prevent duplicates

        Returns:
            job_id: arq job ID string
        """
        if not job_type:
            raise ValueError("job_type cannot be empty")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary")

        queue_name = _PRIORITY_QUEUE_MAP.get(priority, _PRIORITY_QUEUE_MAP["medium"])
        redis_settings = self._get_redis_settings()

        async def _enqueue():
            from arq import create_pool
            pool = await create_pool(redis_settings)
            try:
                job = await pool.enqueue_job(
                    job_type,
                    payload,
                    _job_id=idempotency_key,
                    _queue_name=queue_name,
                )
            finally:
                await pool.aclose()
            if job is None:
                # Duplicate job (idempotency_key already in queue)
                return idempotency_key or ""
            return job.job_id

        return self._run_async(_enqueue())

    def dequeue(self) -> Optional[Job]:
        """
        Not implemented for arq queues.

        arq workers consume jobs internally via the worker process. Callers
        should use the arq CLI or WorkerSettings to start a worker instead.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "arq workers consume jobs internally. "
            "Start an arq worker using backend.job_queue.arq_settings:WorkerSettings."
        )

    def complete(self, job_id: str) -> None:
        """
        No-op: arq tracks job completion via JobResult automatically.

        arq workers store results in Redis upon successful task completion.
        Calling this method is safe but has no effect.
        """
        logger.debug("RedisQueue.complete() called for job %s — no-op (arq manages lifecycle)", job_id)

    def fail(self, job_id: str, error_message: str) -> None:
        """
        No-op: arq tracks job failure via JobResult automatically.

        arq workers store error results in Redis when a task raises an exception.
        Calling this method is safe but has no effect.
        """
        logger.debug(
            "RedisQueue.fail() called for job %s ('%s') — no-op (arq manages lifecycle)",
            job_id,
            error_message,
        )

    def get_pending_count(self) -> int:
        """
        Return the number of jobs currently queued (across all priority queues).

        Uses arq pool's queued_jobs() method.
        """
        redis_settings = self._get_redis_settings()

        async def _count():
            from arq import create_pool
            pool = await create_pool(redis_settings)
            try:
                jobs = await pool.queued_jobs()
                return len(jobs)
            finally:
                await pool.aclose()

        try:
            return self._run_async(_count())
        except Exception as exc:
            logger.warning("RedisQueue.get_pending_count() failed: %s", exc)
            return 0
