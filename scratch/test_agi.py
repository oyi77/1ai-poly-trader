import asyncio
import logging
from backend.models.database import SessionLocal
from backend.core.agi_orchestrator import AGIOrchestrator

async def test():
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        orchestrator = AGIOrchestrator(session=db)
        print("Running AGI cycle...")
        result = await orchestrator.run_cycle()
        print(f"Regime: {result.regime.value}")
        print(f"Goal: {result.goal.value}")
        print(f"Actions: {result.actions_taken}")
        if result.errors:
            print("Errors:", result.errors)
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test())
