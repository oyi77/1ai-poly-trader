import asyncio
import logging
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

logging.basicConfig(level=logging.INFO)

async def test_order():
    # Test WITHOUT funder
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live",
        signature_type=0
        # NOT passing builder_address or builder_api_key etc.
    )
    
    try:
        # 1. Derive credentials
        creds = await clob.create_or_derive_api_creds()
        print(f"Creds derived: {creds is not None}")
        
        # 2. Use a valid token_id
        token_id = "36161990524808999529099890841186860907449767867066339846328156147773282747583"
        print(f"Testing WITHOUT funder, signature_type=0")
        
        # 3. Place order
        result = await clob.place_limit_order(
            token_id=token_id,
            price=0.01,
            size=10.0,
            side="BUY"
        )
        print(f"Order Result: {result}")
        
    except Exception as e:
        print(f"Failed: {type(e).__name__} - {e}")
    finally:
        await clob.__aexit__(None, None, None)
        
if __name__ == "__main__":
    asyncio.run(test_order())
