import asyncio
import logging
from backend.strategies.agi_meta_strategy import AGIMetaStrategy
from backend.strategies.base import StrategyContext
from backend.models.database import SessionLocal
from backend.config import settings
from backend.data.polymarket_clob import clob_from_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_agi")

async def test_agi():
    strategy = AGIMetaStrategy()
    db = SessionLocal()
    clob = clob_from_settings(mode="live")
    
    ctx = StrategyContext(
        db=db, 
        clob=clob,
        settings=settings,
        logger=logger,
        params={},
        mode="live"
    )
    
    try:
        print("Starting AGI Cycle manually...")
        result = await strategy.run_cycle(ctx)
        print(f"AGI Cycle Result: {result}")
    except Exception as e:
        print(f"AGI Cycle Failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_agi())
