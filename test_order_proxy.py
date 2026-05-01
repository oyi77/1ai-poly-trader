import asyncio
import logging
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

logging.basicConfig(level=logging.INFO)

async def test_order():
    # Force signature_type 1 (Proxy) and use builder address
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live",
        signature_type=1,
        builder_address=settings.POLYMARKET_BUILDER_ADDRESS
    )
    
    async with clob:
        try:
            await clob.create_or_derive_api_creds()
            token_id = "36161990524808999529099890841186860907449767867066339846328156147773282747583"
            
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
