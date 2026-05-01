import asyncio
import logging
import json
import sys
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
import py_clob_client.http_helpers.helpers as helpers

# Set up logging to capture everything
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("debug_logger")

# Monkey-patch helpers.request
original_request = helpers.request

def patched_request(endpoint, method, headers=None, data=None):
    logger.info(f"DEBUG {method} to {endpoint}")
    logger.info(f"DEBUG Headers: {headers}")
    if data:
        logger.info(f"DEBUG Data: {data}")
    return original_request(endpoint, method, headers, data)

helpers.request = patched_request

async def test_order():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live",
        signature_type=0
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
