import asyncio
import logging
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

logging.basicConfig(level=logging.INFO)

async def test_order():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live",
        signature_type=0
    )
    
    async with clob:
        try:
            await clob.create_or_derive_api_creds()
            # New token from sampling
            token_id = "78433024518676680431174478322854148606578065650008220678402966840627347604025"
            
            result = await clob.place_limit_order(
                token_id=token_id,
                price=0.01,
                size=10.0,
                side="BUY"
            )
            print(f"Order Result: {result}")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_order())
