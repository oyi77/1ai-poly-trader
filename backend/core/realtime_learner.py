from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.database import Trade

logger = logging.getLogger("trading_bot.realtime_learner")

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# How many settled trades must accumulate before we trigger optimisation.
TRADES_PER_UPDATE: int = 5

# Even if TRADES_PER_UPDATE hasn't been reached, run if this many seconds
# have passed since the last optimisation attempt.
MAX_IDLE_SECONDS: int = 3600  # 1 hour

# Minimum trades in the DB before we attempt any optimisation (cold-start guard).
MIN_TRADES_FOR_OPT: int = 30

# ---------------------------------------------------------------------------
# Module-level state (single process, no Redis needed)
# ---------------------------------------------------------------------------

_trades_since_last_run: int = 0
_last_run_ts: float = 0.0          # epoch seconds
_optimisation_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def on_trade_settled(trade: "Trade", db: "Session") -> None:
    """Fire-and-forget hook called after every trade settlement.

    Safe to call from sync code via ``asyncio.create_task``.
    Never raises — exceptions are logged and swallowed.
    """
    global _trades_since_last_run

    try:
        _trades_since_last_run += 1
        mode = getattr(trade, "trading_mode", "paper") or "paper"
        result = getattr(trade, "result", "unknown") or "unknown"
        pnl = float(getattr(trade, "pnl", 0.0) or 0.0)
        edge = float(getattr(trade, "edge_at_entry", 0.0) or 0.0)
        strategy = getattr(trade, "strategy", "unknown") or "unknown"

        logger.debug(
            "[realtime_learner] trade settled: mode=%s result=%s pnl=%.4f "
            "edge=%.4f strategy=%s accumulated=%d",
            mode, result, pnl, edge, strategy, _trades_since_last_run,
        )

        # Always write the individual outcome to BigBrain for long-term memory.
        await _write_reward_to_brain(trade, mode, result, pnl, edge, strategy)

        # Log per-strategy outcome for monitoring
        reward = (1.0 if pnl > 0 else (-1.0 if pnl < 0 else 0.0)) * max(abs(edge), 0.01)
        logger.info(
            "[%s] mode=%s result=%s pnl=%.2f edge=%.4f reward=%.2f",
            strategy, mode, result, pnl, edge, reward,
        )

        # Decide whether to trigger a parameter optimisation cycle.
        now = time.monotonic()
        idle_seconds = now - _last_run_ts
        should_run = (
            _trades_since_last_run >= TRADES_PER_UPDATE
            or (idle_seconds >= MAX_IDLE_SECONDS and _last_run_ts > 0)
        )

        if should_run:
            if _optimisation_lock.locked():
                logger.debug("[realtime_learner] optimisation already running, skipping trigger")
                return
            asyncio.create_task(_run_optimisation_cycle(db))

    except Exception as exc:
        logger.debug("[realtime_learner] on_trade_settled error (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _write_reward_to_brain(
    trade: "Trade",
    mode: str,
    result: str,
    pnl: float,
    edge: float,
    strategy: str,
) -> None:
    """Write a single trade reward signal to BigBrain."""
    try:
        from backend.clients.bigbrain import get_bigbrain

        brain = get_bigbrain()
        # Compute a scalar reward:  sign(pnl) * edge gives stronger signal
        # when the edge prediction was also large.
        reward = (1.0 if pnl > 0 else (-1.0 if pnl < 0 else 0.0)) * max(abs(edge), 0.01)

        await brain.write_trade_outcome(
            {
                "strategy": strategy,
                "market": getattr(trade, "market_ticker", "unknown"),
                "direction": getattr(trade, "direction", "unknown"),
                "result": result,
                "pnl": pnl,
                "edge": edge,
                "confidence": getattr(trade, "confidence", 0.5),
                "reward": reward,
                "trading_mode": mode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        await brain.close()
    except Exception as exc:
        logger.debug("[realtime_learner] BigBrain write failed (non-fatal): %s", exc)


async def _run_optimisation_cycle(db: "Session") -> None:
    """Global parameter optimization disabled in v2.

    Per-strategy tuning now handled by individual strategy parameter management.
    This stub exists to prevent errors during transition period.
    """
    global _trades_since_last_run, _last_run_ts

    async with _optimisation_lock:
        _trades_since_last_run = 0
        _last_run_ts = time.monotonic()
        logger.info("[realtime_learner] global param optimization disabled — per-strategy tuning in v2")
