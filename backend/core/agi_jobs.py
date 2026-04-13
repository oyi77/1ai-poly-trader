"""Scheduled job wrappers for AGI-loop components (self-review, research)."""

import logging

logger = logging.getLogger("trading_bot")


async def self_review_job() -> None:
    """Run the self-review cycle: attribution, postmortems, degradation detection."""
    from backend.core.scheduler import log_event

    log_event("info", "Running self-review cycle...")
    try:
        from backend.ai.self_review import SelfReview

        reviewer = SelfReview()
        result = await reviewer.run_review_cycle()

        n_alerts = len(result.get("degradation_alerts", []))
        n_postmortems = len(result.get("postmortems", []))
        log_event(
            "success",
            f"Self-review complete: {n_postmortems} postmortems, {n_alerts} degradation alerts",
        )
    except Exception as exc:
        logger.exception("self_review_job failed: %s", exc)
        log_event("error", f"Self-review failed: {exc}")


async def research_pipeline_job() -> None:
    """Run the autonomous research pipeline: RSS, BigBrain search, scoring."""
    from backend.core.scheduler import log_event

    log_event("info", "Running research pipeline...")
    try:
        from backend.research.pipeline import ResearchPipeline

        pipeline = ResearchPipeline()
        items = await pipeline.run_research_cycle()

        log_event(
            "success",
            f"Research pipeline complete: {len(items)} relevant items found",
        )
    except Exception as exc:
        logger.exception("research_pipeline_job failed: %s", exc)
        log_event("error", f"Research pipeline failed: {exc}")
