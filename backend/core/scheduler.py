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
from backend.queue.worker import Worker
from backend.queue.sqlite_queue import AsyncSQLiteQueue

from backend.core.scheduling_strategies import (
    scan_and_trade_job,
    weather_scan_and_trade_job,
    settlement_job,
    news_feed_scan_job,
    arbitrage_scan_job,
    auto_trader_job,
    heartbeat_job,
    strategy_cycle_job,
)
from backend.core.auto_improve import auto_improve_job
from backend.core.strategy_ranker import strategy_ranking_job
from backend.core.agi_jobs import self_review_job, research_pipeline_job
from backend.core.db_backup import backup_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trading_bot")

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None

# Global queue and worker instances
queue: Optional[AsyncSQLiteQueue] = None
worker: Optional[Worker] = None
worker_task: Optional[asyncio.Task] = None

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


def schedule_strategy(strategy_name: str, interval_seconds: int) -> None:
    """Add or replace a strategy's APScheduler job."""
    global scheduler
    if scheduler is None or not scheduler.running:
        return

    job_id = f"strategy_{strategy_name}"
    # functools.partial(async_fn) loses iscoroutinefunction → APScheduler won't await it
    # misfire_grace_time must be generous for long-interval strategies (e.g. 300s, 600s)
    # so that a small scheduler delay doesn't permanently skip the run.
    grace = max(60, interval_seconds // 2)
    scheduler.add_job(
        strategy_cycle_job,
        IntervalTrigger(seconds=interval_seconds),
        args=[strategy_name],
        id=job_id,
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
    logger.info(
        f"Scheduled strategy {strategy_name} every {interval_seconds}s (job_id={job_id})"
    )


def unschedule_strategy(strategy_name: str) -> None:
    """Remove a strategy's APScheduler job."""
    global scheduler
    if scheduler is None or not scheduler.running:
        return
    job_id = f"strategy_{strategy_name}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Unscheduled strategy {strategy_name}")
    except Exception:
        logger.warning(f"Failed to unschedule strategy {strategy_name}")


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
    """Read StrategyConfig table and schedule enabled strategies."""
    from backend.models.database import SessionLocal, StrategyConfig

    db = SessionLocal()
    try:
        configs = db.query(StrategyConfig).filter(StrategyConfig.enabled == True).all()
        for cfg in configs:
            schedule_strategy(cfg.strategy_name, cfg.interval_seconds or 60)
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

    # BTC scan job
    scheduler.add_job(
        scan_and_trade_job,
        IntervalTrigger(seconds=scan_seconds),
        id="market_scan",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    # Weather scan job (only if enabled)
    if getattr(settings, "WEATHER_ENABLED", True):
        weather_seconds = getattr(settings, "WEATHER_SCAN_INTERVAL_SECONDS", 600)
        scheduler.add_job(
            weather_scan_and_trade_job,
            IntervalTrigger(seconds=weather_seconds),
            id="weather_scan",
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
        scheduler.add_job(
            auto_trader_job,
            IntervalTrigger(seconds=60),
            id="auto_trader",
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

    # Initialize queue worker if enabled
    if settings.JOB_WORKER_ENABLED:
        logger.info("JOB_WORKER_ENABLED=True - initializing queue worker")

        # Create queue and worker instances
        queue = AsyncSQLiteQueue(max_workers=settings.DB_EXECUTOR_MAX_WORKERS)
        worker = Worker(queue, max_concurrent=settings.MAX_CONCURRENT_JOBS)

        # Remove APScheduler jobs to prevent double-execution
        # The worker will process jobs from the queue instead
        # Note: weather_scan is NOT removed - it continues via APScheduler
        # because there's no queue handler for it yet
        jobs_to_remove = ["market_scan", "settlement_check"]
        for job_id in jobs_to_remove:
            try:
                scheduler.remove_job(job_id)
                logger.info(
                    f"Removed APScheduler job '{job_id}' - worker will handle via queue"
                )
            except Exception as e:
                logger.warning(f"Could not remove job '{job_id}': {e}")

        # Start worker in background
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
        worker.stop()
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


async def run_manual_scan():
    """Trigger a manual market scan."""
    log_event("info", "Manual scan triggered")
    await scan_and_trade_job()


async def run_manual_settlement():
    """Trigger a manual settlement check."""
    log_event("info", "Manual settlement triggered")
    await settlement_job()
