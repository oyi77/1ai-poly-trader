import asyncio
import logging
import sys
from backend.research.pipeline import AutonomousResearchPipeline

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def test_agi():
    pipeline = AutonomousResearchPipeline()
    print("Running AGI research cycle...")
    
    # Run cycle with a sample market query
    results = await pipeline.run_research_cycle(markets=["Will Bitcoin hit $100k?"])
    
    if results:
        print(f"Research successful: {len(results)} items found.")
        for item in results[:3]:
            print(f"- {item.title} (relevance={item.relevance_score:.2f})")
    else:
        print("No research results found.")

if __name__ == "__main__":
    asyncio.run(test_agi())
