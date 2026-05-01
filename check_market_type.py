import asyncio
import json
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

async def check_market():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live"
    )
    
    async with clob:
        try:
            markets = await asyncio.to_thread(clob._clob_client.get_sampling_simplified_markets)
            print(f"Type of markets: {type(markets)}")
            if isinstance(markets, list) and len(markets) > 0:
                print(f"Type of first element: {type(markets[0])}")
                print(f"First element: {markets[0]}")
            else:
                print(f"Markets content: {markets[:200] if isinstance(markets, str) else markets}")
                
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(check_market())
