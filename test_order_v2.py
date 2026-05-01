import asyncio
import logging
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
from py_order_utils.builders.base_builder import BaseBuilder
from poly_eip712_structs import make_domain

logging.basicConfig(level=logging.INFO)

# Monkey-patch BaseBuilder to use version="2"
original_get_domain_separator = BaseBuilder._get_domain_separator

def patched_get_domain_separator(self, chain_id: int, verifying_contract: str):
    print(f"PATCHED: Using version='2' for contract {verifying_contract}")
    return make_domain(
        name="Polymarket CTF Exchange",
        version="2",
        chainId=str(chain_id),
        verifyingContract=verifying_contract,
    )

BaseBuilder._get_domain_separator = patched_get_domain_separator

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
