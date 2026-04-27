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
    """Run a full parameter optimisation cycle.

    Protected by ``_optimisation_lock`` so only one cycle runs at a time even
    if many trades settle simultaneously.
    """
    global _trades_since_last_run, _last_run_ts

    async with _optimisation_lock:
        _trades_since_last_run = 0
        _last_run_ts = time.monotonic()

        logger.info("[realtime_learner] starting optimisation cycle")

        try:
            from backend.config import settings
            from backend.ai.optimizer import ParameterOptimizer
            from backend.clients.bigbrain import get_bigbrain
            from backend.core.auto_improve import (
                check_rollback_needed,
                validate_and_clamp_params,
                apply_params_to_settings,
                _get_current_params,
                _last_param_change,
                MIN_CONFIDENCE_FOR_AUTO_APPLY,
                _confidence_to_float,
            )

            brain = get_bigbrain()

            try:
                # ── Rollback check ────────────────────────────────────────
                if _last_param_change is not None:
                    rolled_back = check_rollback_needed(db, bigbrain=brain)
                    if rolled_back:
                        logger.warning(
                            "[realtime_learner] rolled back previous parameter change"
                        )
                        return

                optimizer = ParameterOptimizer(settings)
                analysis = optimizer.analyze_performance(db, trade_limit=100)

                if analysis["total_trades"] < MIN_TRADES_FOR_OPT:
                    logger.info(
                        "[realtime_learner] only %d trades (need %d), skipping param opt",
                        analysis["total_trades"], MIN_TRADES_FOR_OPT,
                    )
                    return

                logger.info(
                    "[realtime_learner] analysis: %d trades, %.1f%% win rate, $%.2f pnl",
                    analysis["total_trades"],
                    analysis["win_rate"] * 100,
                    analysis["pnl"],
                )

                suggestions = await optimizer.get_suggestions(db)

                if suggestions.get("status") != "ok":
                    logger.debug("[realtime_learner] optimizer returned non-ok status, skipping")
                    return

                params = suggestions.get("suggestions", {})
                confidence = params.get("confidence", "low")
                reasoning = params.get("reasoning", "")
                conf_float = _confidence_to_float(confidence)

                # ── Write insight to BigBrain ─────────────────────────────
                await brain.write_strategy_insight(
                    strategy="realtime_learner",
                    insight=(
                        f"Realtime opt: edge={params.get('min_edge_threshold')} "
                        f"kelly={params.get('kelly_fraction')} "
                        f"reason={reasoning}"
                    ),
                    confidence=confidence,
                )

                await brain.write_parameter_tuning(
                    params={
                        "kelly_fraction": params.get("kelly_fraction"),
                        "min_edge_threshold": params.get("min_edge_threshold"),
                        "max_trade_size": params.get("max_trade_size"),
                        "daily_loss_limit": params.get("daily_loss_limit"),
                    },
                    win_rate=analysis["win_rate"],
                    pnl=analysis["pnl"],
                    confidence=confidence,
                )

                # ── Auto-apply with existing guardrails ───────────────────
                import backend.core.auto_improve as _aim

                if conf_float >= MIN_CONFIDENCE_FOR_AUTO_APPLY and _aim._last_param_change is None:
                    from backend.models.database import Trade as TradeModel

                    current_params = _get_current_params()
                    suggested_params = {
                        k: params.get(k)
                        for k in ("kelly_fraction", "min_edge_threshold", "max_trade_size", "daily_loss_limit")
                        if params.get(k) is not None
                    }
                    clamped = validate_and_clamp_params(current_params, suggested_params)

                    if clamped:
                        previous = apply_params_to_settings(clamped)

                        total_settled = (
                            db.query(TradeModel)
                            .filter(
                                TradeModel.settled.is_(True),
                                TradeModel.result.in_(("win", "loss")),
                            )
                            .count()
                        )

                        import json as _json
                        _aim._last_param_change = {
                            "previous_values": previous,
                            "applied_values": clamped,
                            "applied_at": datetime.now(timezone.utc),
                            "pre_change_win_rate": analysis["win_rate"],
                            "pre_change_pnl": analysis["pnl"],
                            "trade_count_at_apply": total_settled,
                        }

                        try:
                            from backend.models.database import log_audit
                            log_audit(
                                action="realtime_learner_apply",
                                actor="realtime_learner",
                                details={
                                    "previous": previous,
                                    "applied": clamped,
                                    "confidence": conf_float,
                                    "reasoning": reasoning[:300],
                                },
                            )
                        except Exception:
                            pass

                        await brain.send_alert(
                            f"⚡ REALTIME LEARNER APPLIED: {_json.dumps(clamped)} "
                            f"(confidence={conf_float:.2f}, reason={reasoning[:150]})",
                            level="info",
                        )
                        logger.info(
                            "[realtime_learner] applied params (conf=%.2f): %s",
                            conf_float, _json.dumps(clamped),
                        )
                    else:
                        logger.info("[realtime_learner] no valid param changes to apply")
                else:
                    if _aim._last_param_change is not None:
                        logger.info(
                            "[realtime_learner] previous change still pending rollback eval, skipping apply"
                        )
                    else:
                        logger.info(
                            "[realtime_learner] confidence %s (%.2f) below threshold, not applying",
                            confidence, conf_float,
                        )

            finally:
                await brain.close()

        except Exception as exc:
            logger.warning("[realtime_learner] optimisation cycle error: %s", exc, exc_info=True)
