import asyncio
import logging
import json
import sys
import uuid
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
import py_order_utils.builders.order_builder as order_builder_mod

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Monkey-patch salt_generator to return a large 256-bit integer
def large_salt_generator():
    salt = uuid.uuid4().int
    print(f"GENERATING LARGE SALT: {salt}")
    return salt

# We need to find where salt_generator is used.
# In OrderBuilder.__init__, it's passed as an argument.
# But OrderBuilder is initialized inside py_clob_client.order_builder.builder.OrderBuilder.create_order.

import py_clob_client.order_builder.builder as builder_mod

original_create_order = builder_mod.OrderBuilder.create_order

def patched_create_order(self, order_args, options):
    # We'll patch the salt_generator on the fly if possible, 
    # but it's easier to just patch the OrderData creation.
    # Actually, let's patch py_order_utils.builders.order_builder.generate_seed
    return original_create_order(self, order_args, options)

import py_order_utils.builders.order_builder as utils_builder_mod
import py_order_utils.utils as utils_mod

utils_mod.generate_seed = large_salt_generator
utils_builder_mod.generate_seed = large_salt_generator

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
