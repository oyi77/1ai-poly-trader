import asyncio
import json
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

async def get_recent_token():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live"
    )
    
    async with clob:
        try:
            markets = await asyncio.to_thread(clob._clob_client.get_sampling_simplified_markets)
            print(f"MARKETS_DATA: {str(markets)[:500]}")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(get_recent_token())
