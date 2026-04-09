import asyncio
import functools
import logging
import time
from enum import Enum
from typing import Any, Callable

from backend.core.errors import CircuitOpenError

logger = logging.getLogger(__name__)


class State(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._state = State.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.last_state_change: float = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        if self._state == State.OPEN:
            if (
                self.last_failure_time is not None
                and time.monotonic() - self.last_failure_time >= self.recovery_timeout
            ):
                return State.HALF_OPEN
        return self._state

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        current_state = self.state

        if current_state == State.OPEN:
            raise CircuitOpenError(self.name)

        async with self._lock:
            if self._state == State.OPEN and self.state == State.HALF_OPEN:
                self._transition(State.HALF_OPEN)

        try:
            result = await func(*args, **kwargs)
        except Exception:
            await self._on_failure()
            raise

        await self._on_success()
        return result

    def __call__(self, func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self.call(func, *args, **kwargs)
        return wrapper

    def reset(self) -> None:
        self._state = State.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_state_change = time.monotonic()
        logger.warning("CircuitBreaker '%s': manually reset to CLOSED", self.name)

    async def _on_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            current_state = self._state
            if current_state == State.HALF_OPEN:
                self._transition(State.OPEN)
            elif current_state == State.CLOSED and self.failure_count >= self.failure_threshold:
                self._transition(State.OPEN)

    async def _on_success(self) -> None:
        async with self._lock:
            current_state = self._state

            if current_state == State.HALF_OPEN or (
                current_state == State.OPEN and self.state == State.HALF_OPEN
            ):
                self.success_count += 1
                if self.success_count >= self.half_open_max:
                    self._transition(State.CLOSED)
            elif current_state == State.CLOSED:
                self.failure_count = 0

    def _transition(self, new_state: State) -> None:
        old_state = self._state
        self._state = new_state
        self.last_state_change = time.monotonic()

        if new_state == State.CLOSED:
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None

        logger.warning(
            "CircuitBreaker '%s': %s -> %s",
            self.name,
            old_state,
            new_state,
        )
