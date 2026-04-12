"""Auto-improvement job for PolyEdge - learns from trade outcomes."""

import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.models.database import SessionLocal, Trade, DecisionLog, BotState
from backend.ai.optimizer import ParameterOptimizer
from backend.clients.bigbrain import get_bigbrain

logger = logging.getLogger("trading_bot")


async def auto_improve_job():
    """
    Weekly job that:
    1. Analyzes recent trade outcomes
    2. Writes insights to BigBrain
    3. Gets AI parameter suggestions
    4. Writes parameter tuning results to brain
    """
    from backend.core.scheduler import log_event

    log_event("info", "Running auto-improvement analysis...")

    db = SessionLocal()
    bigbrain = get_bigbrain()

    try:
        optimizer = ParameterOptimizer(settings)
        analysis = optimizer.analyze_performance(db, trade_limit=100)

        log_event(
            "data",
            f"Performance: {analysis['total_trades']} trades, {analysis['win_rate']:.1%} win rate, ${analysis['pnl']:.2f} P&L",
        )

        # Min sample gate: skip parameter changes with insufficient data
        MIN_TRADES_FOR_OPTIMIZATION = 30
        if analysis["total_trades"] < MIN_TRADES_FOR_OPTIMIZATION:
            log_event(
                "info",
                f"Auto-improve: only {analysis['total_trades']} trades "
                f"(need {MIN_TRADES_FOR_OPTIMIZATION}), skipping parameter optimization"
            )
            await _write_outcomes_to_brain(db, bigbrain)
            await _write_market_insights(db, bigbrain)
            log_event("success", "Auto-improvement cycle complete (data collection only)")
            return

        await _write_outcomes_to_brain(db, bigbrain)

        suggestions = await optimizer.get_suggestions(db)

        if suggestions.get("status") == "ok":
            params = suggestions.get("suggestions", {})
            reasoning = params.get("reasoning", "No reasoning provided")
            confidence = params.get("confidence", "low")

            # Track parameter changes as experiments
            try:
                from backend.core.experiment_tracker import experiment_tracker
                exp_id = experiment_tracker.create_experiment(
                    db, "auto_improve", params,
                    notes=f"AI suggested ({confidence}): {reasoning[:200]}",
                )
                experiment_tracker.record_metrics(db, exp_id, {
                    "win_rate": analysis["win_rate"],
                    "pnl": analysis["pnl"],
                    "total_trades": analysis["total_trades"],
                    "confidence": confidence,
                })
            except Exception as e:
                logger.debug(f"Experiment tracking failed: {e}")

            await bigbrain.write_strategy_insight(
                strategy="parameter_optimizer",
                insight=f"Suggested: edge={params.get('min_edge_threshold')}, kelly={params.get('kelly_fraction')}, reasoning={reasoning}",
                confidence=confidence,
            )

            await bigbrain.write_parameter_tuning(
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

            log_event(
                "success", f"Auto-improve: {confidence} confidence - {reasoning[:100]}"
            )

        await _write_market_insights(db, bigbrain)

        # AGI pattern: run strategy evolution cycle (logs proposals, never auto-applies)
        try:
            from backend.agents.autoresearch.evolver import StrategyEvolver

            evolver = StrategyEvolver()
            proposals = await evolver.run_evolution_cycle(db)
            if proposals:
                log_event(
                    "info",
                    f"Evolution: {len(proposals)} proposal(s) generated — "
                    "approve via POST /api/agents/experiments/{id}/approve",
                )
        except Exception as _e:
            logger.debug(f"[auto_improve] StrategyEvolver skipped: {_e}")

        log_event("success", "Auto-improvement cycle complete")

    except Exception as e:
        log_event("error", f"Auto-improve error: {e}")
        logger.exception("Error in auto_improve_job")
    finally:
        db.close()
        await bigbrain.close()


async def _write_outcomes_to_brain(db, bigbrain):
    """Write recent trade outcomes to BigBrain."""
    try:
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        trades = (
            db.query(Trade)
            .filter(
                Trade.settled == True,
                Trade.settlement_time >= week_ago,
            )
            .limit(50)
            .all()
        )

        for trade in trades:
            await bigbrain.write_trade_outcome(
                strategy=trade.strategy or "unknown",
                market=trade.market_ticker,
                direction=trade.direction,
                result=trade.result or "unknown",
                pnl=trade.pnl or 0.0,
                edge=trade.edge_at_entry or 0.0,
                confidence=getattr(trade, "confidence", 0.5),
                timestamp=trade.settlement_time.isoformat()
                if trade.settlement_time
                else None,
            )
    except Exception as e:
        logger.warning(f"Failed to write outcomes to brain: {e}")


async def _write_market_insights(db, bigbrain):
    """Write market analysis insights to BigBrain."""
    try:
        recent_signals = (
            db.query(DecisionLog)
            .filter(
                DecisionLog.decision == "BUY",
            )
            .order_by(DecisionLog.created_at.desc())
            .limit(20)
            .all()
        )

        for sig in recent_signals:
            if sig.signal_data:
                try:
                    data = (
                        json.loads(sig.signal_data)
                        if isinstance(sig.signal_data, str)
                        else sig.signal_data
                    )
                    prob = data.get("model_probability", 0.5)
                    edge = data.get("edge", 0.0)
                    direction = data.get("direction", "up")

                    await bigbrain.write_signal_analysis(
                        market=sig.market_ticker,
                        direction=direction,
                        probability=prob,
                        edge=edge,
                        reasoning=f"Signal from {sig.strategy}",
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Failed to write market insights: {e}")
