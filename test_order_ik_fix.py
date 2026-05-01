import asyncio
import logging
import json
import sys
import uuid
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
import py_clob_client.utilities as utilities
import py_clob_client.client as clob_module

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("debug_logger")

# Monkey-patch order_to_json to include idempotencyKey
def patched_order_to_json(order, owner, orderType, post_only=False):
    # Use the salt as a base for the idempotency key if possible, 
    # or just generate a new UUID and hope for the best.
    # Actually, many systems expect salt == idempotencyKey (as int)
    ik = str(uuid.uuid4())
    print(f"PATCHING order_to_json with idempotencyKey: {ik}")
    return {
        "order": order.dict(), 
        "owner": owner, 
        "orderType": orderType, 
        "postOnly": post_only,
        "idempotencyKey": ik # <--- ADDED
    }

utilities.order_to_json = patched_order_to_json

# Also need to patch it in the client if it was already imported
clob_module.order_to_json = patched_order_to_json

async def test_order():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live",
        signature_type=0
    )
    
    async with clob:
        try:
            await clob.create_or_derive_api_creds()
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
