import asyncio
import logging
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.ai.debate_router import run_debate_with_routing
from backend.models.database import Base

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def test_debate():
    # Setup in-memory DB for settings
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        question = "Will Bitcoin hit $100k by May 2026?"
        market_price = 0.45
        
        print(f"Running debate for: {question}")
        result = await run_debate_with_routing(
            db=db,
            question=question,
            market_price=market_price,
            volume=1000000,
            category="crypto",
            context="Bitcoin is currently at $65k. Halving just happened."
        )
        
        if result:
            print(f"Debate Result: {result.consensus_probability:.3f}")
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Reasoning: {result.reasoning[:200]}...")
        else:
            print("Debate failed to return a result.")
            
    except Exception as e:
        print(f"Debate Test Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_debate())
