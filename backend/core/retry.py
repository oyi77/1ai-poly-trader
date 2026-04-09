"""Retry decorator with exponential backoff for transient failures."""
import asyncio
import functools
import logging
import random
import time
from typing import Callable

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Callable | None = None,
):
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exc = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except retryable_exceptions as exc:
                        last_exc = exc
                        if attempt == max_attempts:
                            break
                        delay = min(backoff_base ** attempt, max_delay) + random.random()
                        logger.warning(
                            "Retry %d/%d for %s after %.1fs: %s",
                            attempt, max_attempts, func.__name__, delay, exc,
                        )
                        if on_retry is not None:
                            on_retry(func.__name__, attempt, exc)
                        await asyncio.sleep(delay)
                raise last_exc
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exc = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except retryable_exceptions as exc:
                        last_exc = exc
                        if attempt == max_attempts:
                            break
                        delay = min(backoff_base ** attempt, max_delay) + random.random()
                        logger.warning(
                            "Retry %d/%d for %s after %.1fs: %s",
                            attempt, max_attempts, func.__name__, delay, exc,
                        )
                        if on_retry is not None:
                            on_retry(func.__name__, attempt, exc)
                        time.sleep(delay)
                raise last_exc
            return sync_wrapper

    return decorator
