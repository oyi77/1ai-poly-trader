import asyncio
import logging
import json
import sys
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
import py_order_utils.builders.base_builder as base_builder
from poly_eip712_structs import make_domain

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Monkey-patch BaseBuilder._get_domain_separator to use version="2"
def patched_get_domain_separator(self, chain_id: int, verifying_contract: str):
    print(f"FORCING EIP-712 Domain Version: 2")
    return make_domain(
        name="Polymarket CTF Exchange",
        version="2", # <--- CHANGE FROM "1" to "2"
        chainId=str(chain_id),
        verifyingContract=verifying_contract,
    )

base_builder.BaseBuilder._get_domain_separator = patched_get_domain_separator

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
