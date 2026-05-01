"""Auto-retraining trigger — fires after sufficient settled trades or Brier degradation."""
import asyncio
import logging
from backend.models.database import SessionLocal, Trade

logger = logging.getLogger("trading_bot.retrain")


async def check_and_trigger_retraining() -> dict:
    try:
        db = SessionLocal()
        try:
            settled_count = db.query(Trade).filter(Trade.settled == True).count()
            if settled_count < 50:
                return {"status": "skipped", "reason": f"only {settled_count} settled trades, need 50"}
            from backend.ai.training.train import run_training_pipeline
            result = await run_training_pipeline(min_examples=200)
            if result["status"] == "ok":
                try:
                    from backend.ai.prediction_engine import PredictionEngine
                    old_accuracy = getattr(PredictionEngine, '_last_accuracy', 0.0)
                    if result["accuracy"] >= old_accuracy:
                        PredictionEngine._last_accuracy = result["accuracy"]
                        logger.info(f"Retraining accepted: acc={result['accuracy']:.3f} >= {old_accuracy:.3f}")
                    else:
                        logger.warning(f"Retraining rejected: acc={result['accuracy']:.3f} < {old_accuracy:.3f}")
                        result["status"] = "degraded"
                except Exception:
                    pass
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Retrain trigger failed: {e}")
        return {"status": "error", "reason": str(e)}
