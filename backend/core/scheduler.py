"""Background scheduler for BTC 5-min autonomous trading.

This module manages the APScheduler instance and scheduling configuration.
The actual job functions are in scheduling_strategies.py.
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

from backend.config import settings
from backend.job_queue.worker import Worker
from backend.job_queue.sqlite_queue import AsyncSQLiteQueue
from backend.core.task_manager import TaskManager

from backend.core.scheduling_strategies import (
    scan_and_trade_job,
    weather_scan_and_trade_job,
    settlement_job,
    news_feed_scan_job,
    arbitrage_scan_job,
    auto_trader_job,
    heartbeat_job,
    strategy_cycle_job,
    sync_testnet_wallet,
    sync_live_wallet,
    verify_settlement_blockchain,
)
from backend.core.auto_improve import auto_improve_job
from backend.core.strategy_ranker import strategy_ranking_job
from backend.core.agi_jobs import self_review_job, research_pipeline_job
from backend.core.db_backup import backup_job
from backend.core.cache_cleanup import cache_cleanup_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trading_bot")

scheduler: Optional[AsyncIOScheduler] = None

queue: Optional[AsyncSQLiteQueue] = None
worker: Optional[Worker] = None
worker_task: Optional[asyncio.Task] = None
task_manager: Optional[TaskManager] = None

# Event log for terminal display (in-memory, last 200 events)
event_log: List[dict] = []
MAX_LOG_SIZE = 200


def log_event(event_type: str, message: str, data: dict = None):
    """Log an event for terminal display."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "message": message,
        "data": data or {},
    }
    event_log.append(event)

    while len(event_log) > MAX_LOG_SIZE:
        event_log.pop(0)

    log_func = {
        "error": logger.error,
        "warning": logger.warning,
        "success": logger.info,
        "info": logger.info,
        "data": logger.debug,
        "trade": logger.info,
    }.get(event_type, logger.info)

    log_func(f"[{event_type.upper()}] {message}")


def get_recent_events(limit: int = 50) -> List[dict]:
    """Get recent events for terminal display."""
    return event_log[-limit:]


def schedule_strategy(strategy_name: str, interval_seconds: int, mode: str = "paper") -> None:
    """Add or replace a strategy's APScheduler job for a specific mode.
    
    Args:
        strategy_name: Name of the strategy to schedule.
        interval_seconds: Interval between job executions.
        mode: Trading mode ("paper", "testnet", or "live").
    """
    global scheduler
    if scheduler is None or not scheduler.running:
        return

    job_id = f"{mode}_{strategy_name}_{interval_seconds}"
    # functools.partial(async_fn) loses iscoroutinefunction → APScheduler won't await it
    # misfire_grace_time must be generous for long-interval strategies (e.g. 300s, 600s)
    # so that a small scheduler delay doesn't permanently skip the run.
    grace = max(60, interval_seconds // 2)
    scheduler.add_job(
        strategy_cycle_job,
        IntervalTrigger(seconds=interval_seconds),
        kwargs={"strategy_name": strategy_name, "mode": mode},
        id=job_id,
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
    logger.info(
        f"Scheduled strategy {strategy_name} for mode {mode} every {interval_seconds}s (job_id={job_id})"
    )


def unschedule_strategy(strategy_name: str, mode: str = "paper", interval_seconds: int = 60) -> None:
    """Remove a strategy's APScheduler job for a specific mode."""
    global scheduler
    if scheduler is None or not scheduler.running:
        return
    job_id = f"{mode}_{strategy_name}_{interval_seconds}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Unscheduled strategy {strategy_name} for mode {mode}")
    except Exception:
        logger.warning(f"Failed to unschedule strategy {strategy_name} for mode {mode}")


def get_scheduler_jobs() -> list[dict]:
    """Return current scheduled jobs info."""
    global scheduler
    if scheduler is None or not scheduler.running:
        return []
    return [
        {
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in scheduler.get_jobs()
    ]


def _load_strategy_jobs() -> None:
    """Read StrategyConfig table and schedule enabled strategies for all modes."""
    from backend.models.database import SessionLocal, StrategyConfig
    from backend.core.mode_context import list_contexts

    db = SessionLocal()
    try:
        contexts = list_contexts()
        for mode in contexts.keys():
            configs = (
                db.query(StrategyConfig)
                .filter(StrategyConfig.enabled.is_(True))
                .filter(
                    (StrategyConfig.mode == mode) | (StrategyConfig.mode == None)
                )
                .all()
            )
            for cfg in configs:
                schedule_strategy(cfg.strategy_name, cfg.interval_seconds or 60, mode)
    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler for BTC 5-min trading."""
    global scheduler, queue, worker, worker_task

    if scheduler is not None and scheduler.running:
        log_event("warning", "Scheduler already running")
        return

    scheduler = AsyncIOScheduler()

    scan_seconds = settings.SCAN_INTERVAL_SECONDS
    settle_seconds = settings.SETTLEMENT_INTERVAL_SECONDS

    # Check settlements every 2 minutes
    scheduler.add_job(
        settlement_job,
        IntervalTrigger(seconds=settle_seconds),
        id="settlement_check",
        replace_existing=True,
        max_instances=1,
    )

    # Heartbeat every minute
    scheduler.add_job(
        heartbeat_job,
        IntervalTrigger(minutes=1),
        id="heartbeat",
        replace_existing=True,
        max_instances=1,
    )

    from backend.core.mode_context import list_contexts
    contexts = list_contexts()
    modes = list(contexts.keys()) if contexts else ["paper", "testnet", "live"]

    for mode in modes:
        scheduler.add_job(
            scan_and_trade_job,
            IntervalTrigger(seconds=scan_seconds),
            kwargs={"mode": mode},
            id=f"{mode}_market_scan",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=60,
        )

    if getattr(settings, "WEATHER_ENABLED", True):
        weather_seconds = getattr(settings, "WEATHER_SCAN_INTERVAL_SECONDS", 600)
        for mode in modes:
            scheduler.add_job(
                weather_scan_and_trade_job,
                IntervalTrigger(seconds=weather_seconds),
                kwargs={"mode": mode},
                id=f"{mode}_weather_scan",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=120,
            )

    # Watchdog: check strategy heartbeats every 30s
    from backend.core.heartbeat import watchdog_job, wallet_sync_job

    scheduler.add_job(
        watchdog_job,
        IntervalTrigger(seconds=30),
        id="watchdog",
        replace_existing=True,
        max_instances=1,
    )

    # Wallet balance sync: fetch live CLOB balance every 60s
    scheduler.add_job(
        wallet_sync_job,
        IntervalTrigger(seconds=60),
        id="wallet_sync",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        sync_testnet_wallet,
        IntervalTrigger(seconds=60),
        id="wallet_sync_testnet",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        sync_live_wallet,
        IntervalTrigger(seconds=30),
        id="wallet_sync_live",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        verify_settlement_blockchain,
        IntervalTrigger(seconds=120),
        id="settlement_verify",
        replace_existing=True,
        max_instances=1,
    )

    # Start the scheduler
    scheduler.start()
    for job in scheduler.get_jobs():
        logger.info(
            f"scheduler job registered: id={job.id} next_run={job.next_run_time}"
        )
    logger.info(f"scheduler started: jobs={[j.id for j in scheduler.get_jobs()]}")

    if settings.NEWS_FEED_ENABLED:
        scheduler.add_job(
            news_feed_scan_job,
            IntervalTrigger(seconds=settings.NEWS_FEED_INTERVAL_SECONDS),
            id="news_feed_scan",
            replace_existing=True,
            max_instances=1,
        )

    if settings.ARBITRAGE_DETECTOR_ENABLED:
        scheduler.add_job(
            arbitrage_scan_job,
            IntervalTrigger(seconds=settings.ARBITRAGE_SCAN_INTERVAL_SECONDS),
            id="arbitrage_scan",
            replace_existing=True,
            max_instances=1,
        )

    if settings.AUTO_TRADER_ENABLED:
        for mode in modes:
            scheduler.add_job(
                auto_trader_job,
                IntervalTrigger(seconds=60),
                kwargs={"mode": mode},
                id=f"{mode}_auto_trader",
                replace_existing=True,
                max_instances=1,
            )

    # Strategy ranking job - weekly ranking and auto-disable
    scheduler.add_job(
        strategy_ranking_job,
        IntervalTrigger(days=1),
        id="strategy_ranking",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduled daily strategy ranking job")

    # Auto-improvement job - learns from trade outcomes
    if settings.AUTO_IMPROVE_ENABLED:
        from apscheduler.triggers.interval import IntervalTrigger as _IntervalTrigger

        scheduler.add_job(
            auto_improve_job,
            _IntervalTrigger(days=settings.AUTO_IMPROVE_INTERVAL_DAYS),
            id="auto_improve",
            replace_existing=True,
            max_instances=1,
        )

    # Self-review job - daily attribution, postmortems, degradation detection
    if settings.SELF_REVIEW_ENABLED:
        scheduler.add_job(
            self_review_job,
            IntervalTrigger(days=settings.SELF_REVIEW_INTERVAL_DAYS),
            id="self_review",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "Scheduled self-review job every %d day(s)",
            settings.SELF_REVIEW_INTERVAL_DAYS,
        )

    # Research pipeline job - autonomous market research
    if settings.RESEARCH_PIPELINE_ENABLED:
        scheduler.add_job(
            research_pipeline_job,
            IntervalTrigger(hours=settings.RESEARCH_PIPELINE_INTERVAL_HOURS),
            id="research_pipeline",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "Scheduled research pipeline job every %d hour(s)",
            settings.RESEARCH_PIPELINE_INTERVAL_HOURS,
        )

    backup_interval = getattr(settings, "DB_BACKUP_INTERVAL_HOURS", 6)
    if backup_interval > 0:
        scheduler.add_job(
            backup_job,
            IntervalTrigger(hours=backup_interval),
            id="db_backup",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Scheduled database backup job every {backup_interval} hour(s)")

    scheduler.add_job(
        cache_cleanup_job,
        IntervalTrigger(hours=1),
        id="cache_cleanup",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduled cache cleanup job every 1 hour")

    from backend.core.proposal_executor import (
        execute_approved_proposals_job,
        measure_impact_and_rollback_job
    )
    
    scheduler.add_job(
        execute_approved_proposals_job,
        IntervalTrigger(minutes=30),
        id="execute_proposals",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduled proposal execution job every 30 minutes")
    
    scheduler.add_job(
        measure_impact_and_rollback_job,
        IntervalTrigger(hours=2),
        id="measure_impact_rollback",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduled impact measurement and auto-rollback job every 2 hours")

    # Initialize queue worker if enabled
    if settings.JOB_WORKER_ENABLED:
        logger.info("JOB_WORKER_ENABLED=True - initializing queue worker")

        global queue, worker, worker_task, task_manager
        queue = AsyncSQLiteQueue(max_workers=settings.DB_EXECUTOR_MAX_WORKERS)
        
        from backend.api.main import app
        if hasattr(app.state, 'task_manager'):
            task_manager = app.state.task_manager
            worker = Worker(queue, max_concurrent=settings.MAX_CONCURRENT_JOBS, task_manager=task_manager)
        else:
            worker = Worker(queue, max_concurrent=settings.MAX_CONCURRENT_JOBS)

        jobs_to_remove = [f"{mode}_market_scan" for mode in modes] + ["settlement_check"]
        for job_id in jobs_to_remove:
            try:
                scheduler.remove_job(job_id)
                logger.info(
                    f"Removed APScheduler job '{job_id}' - worker will handle via queue"
                )
            except Exception as e:
                logger.warning(f"Could not remove job '{job_id}': {e}")

        if task_manager:
            worker_task = asyncio.create_task(
                task_manager.create_task(worker.start(), name="queue_worker")
            )
        else:
            worker_task = asyncio.create_task(worker.start())
        logger.info("Queue worker started in background")

        log_event(
            "success",
            "BTC 5-min trading scheduler started with queue worker",
            {
                "worker_enabled": True,
                "scan_interval": f"{scan_seconds}s",
                "settlement_interval": f"{settle_seconds}s",
                "min_edge": f"{settings.MIN_EDGE_THRESHOLD:.0%}",
                "weather_enabled": settings.WEATHER_ENABLED,
                "max_concurrent_jobs": settings.MAX_CONCURRENT_JOBS,
            },
        )
    else:
        logger.info("JOB_WORKER_ENABLED=False - using APScheduler for job execution")
        log_event(
            "success",
            "BTC 5-min trading scheduler started",
            {
                "worker_enabled": False,
                "scan_interval": f"{scan_seconds}s",
                "settlement_interval": f"{settle_seconds}s",
                "min_edge": f"{settings.MIN_EDGE_THRESHOLD:.0%}",
                "weather_enabled": settings.WEATHER_ENABLED,
            },
        )

    # Load registry-driven strategy jobs from DB
    try:
        _load_strategy_jobs()
    except Exception as e:
        logger.exception(f"Could not load strategy jobs from DB: {e}")


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler, worker, queue, worker_task

    if scheduler is None or not scheduler.running:
        log_event("info", "Scheduler not running")
        return

    # Stop worker if running
    if worker is not None:
        logger.info("Stopping queue worker...")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(worker.stop())
        except RuntimeError:
            asyncio.run(worker.stop())
        worker = None
        logger.info("Queue worker stopped")

        # Cancel the worker asyncio task to unblock any pending await
        if worker_task is not None and not worker_task.done():
            worker_task.cancel()
            logger.info("Worker task cancelled")
        worker_task = None

        # Shutdown queue
        if queue is not None:
            queue.shutdown()
            queue = None
            logger.info("Queue shutdown complete")

    # Shutdown scheduler
    scheduler.shutdown(wait=False)
    scheduler = None
    log_event("info", "Scheduler stopped")


def is_scheduler_running() -> bool:
    """Check if scheduler is currently running."""
    return scheduler is not None and scheduler.running


def reschedule_jobs() -> list[dict]:
    """Reschedule jobs with current settings values. Call after settings update."""
    from apscheduler.jobstores.base import JobLookupError as _JobLookupError

    global scheduler
    if scheduler is None or not scheduler.running:
        return []

    results = []

    # Reschedule scan job
    try:
        scheduler.reschedule_job(
            "market_scan",
            trigger=IntervalTrigger(seconds=settings.SCAN_INTERVAL_SECONDS),
        )
        job = scheduler.get_job("market_scan")
        results.append(
            {
                "job_id": "market_scan",
                "next_run": str(job.next_run_time) if job else None,
            }
        )
    except _JobLookupError:
        logger.warning("market_scan job not registered, skipping reschedule")
    except Exception as e:
        logger.warning(f"Failed to reschedule market_scan: {e}")

    # Reschedule settlement job
    try:
        scheduler.reschedule_job(
            "settlement_check",
            trigger=IntervalTrigger(seconds=settings.SETTLEMENT_INTERVAL_SECONDS),
        )
        job = scheduler.get_job("settlement_check")
        results.append(
            {
                "job_id": "settlement_check",
                "next_run": str(job.next_run_time) if job else None,
            }
        )
    except _JobLookupError:
        logger.warning("settlement_check job not registered, skipping reschedule")
    except Exception as e:
        logger.warning(f"Failed to reschedule settlement_check: {e}")

    # Reschedule weather scan if enabled
    if settings.WEATHER_ENABLED:
        try:
            scheduler.reschedule_job(
                "weather_scan",
                trigger=IntervalTrigger(seconds=settings.WEATHER_SCAN_INTERVAL_SECONDS),
            )
            job = scheduler.get_job("weather_scan")
            results.append(
                {
                    "job_id": "weather_scan",
                    "next_run": str(job.next_run_time) if job else None,
                }
            )
        except _JobLookupError:
            logger.warning("weather_scan job not registered, skipping reschedule")
        except Exception as e:
            logger.warning(f"Failed to reschedule weather_scan: {e}")

    log_event("info", f"Scheduler jobs rescheduled: {[r['job_id'] for r in results]}")
    return results


async def run_manual_scan(mode: str = "paper"):
    """Trigger a manual market scan."""
    log_event("info", f"Manual scan triggered for mode: {mode}")
    await scan_and_trade_job(mode)


async def run_manual_settlement():
    """Trigger a manual settlement check."""
    log_event("info", "Manual settlement triggered")
    await settlement_job()

# Add monitoring job
async def monitoring_job():
    """Run production monitoring checks"""
    from backend.core.monitoring import run_monitoring_check
    from backend.models.database import get_db
    
    db = next(get_db())
    try:
        health = await run_monitoring_check(db)
        logger.info(f"✅ Monitoring check: {health['database']['healthy']}")
        return health
    except Exception as e:
        logger.error(f"❌ Monitoring check failed: {e}")
    finally:
        db.close()
