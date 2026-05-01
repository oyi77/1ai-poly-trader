import asyncio
import logging
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

logging.basicConfig(level=logging.INFO)

async def test_order():
    # Use the settings as they are currently in .env
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        api_key=settings.POLYMARKET_API_KEY,
        api_secret=settings.POLYMARKET_API_SECRET,
        api_passphrase=settings.POLYMARKET_API_PASSPHRASE,
        mode="live",
        builder_api_key=settings.POLYMARKET_BUILDER_API_KEY,
        builder_secret=settings.POLYMARKET_BUILDER_SECRET,
        builder_passphrase=settings.POLYMARKET_BUILDER_PASSPHRASE,
        builder_address=settings.POLYMARKET_BUILDER_ADDRESS,
        signature_type=settings.POLYMARKET_SIGNATURE_TYPE
    )
    
    try:
        # 1. Derive credentials
        creds = await clob.create_or_derive_api_creds()
        print(f"Creds derived: {creds is not None}")
        
        # 2. Use the valid token_id found via curl
        token_id = "36161990524808999529099890841186860907449767867066339846328156147773282747583"
        print(f"Testing with POLYMARKET_SIGNATURE_TYPE = {settings.POLYMARKET_SIGNATURE_TYPE}")
        print(f"Token ID: {token_id}")
        
        # 3. Place a very small limit order far out of the money
        result = await clob.place_limit_order(
            token_id=token_id,
            price=0.01,
            size=10.0, # Increased size to meet minimum if needed
            side="BUY"
        )
        print(f"Order Result: {result}")
        
    except Exception as e:
        print(f"Failed: {type(e).__name__} - {e}")
    finally:
        await clob.__aexit__(None, None, None)
        
if __name__ == "__main__":
    asyncio.run(test_order())
