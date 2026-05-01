import asyncio
import logging
import json
import sys
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
import py_order_utils.model.order as order_mod
from poly_eip712_structs import Address, EIP712Struct, Uint

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Redefine Order for REAL V1 (No signer, No signatureType)
class RealV1Order(EIP712Struct):
    salt = Uint(256)
    maker = Address()
    taker = Address()
    tokenId = Uint(256)
    makerAmount = Uint(256)
    takerAmount = Uint(256)
    expiration = Uint(256)
    nonce = Uint(256)
    feeRateBps = Uint(256)
    side = Uint(8)

    def dict(self):
        return {
            "salt": self["salt"],
            "maker": self["maker"],
            "taker": self["taker"],
            "tokenId": self["tokenId"],
            "makerAmount": self["makerAmount"],
            "takerAmount": self["takerAmount"],
            "expiration": self["expiration"],
            "nonce": self["nonce"],
            "feeRateBps": self["feeRateBps"],
            "side": self["side"],
        }

# Patch OrderBuilder to use RealV1Order
order_mod.Order = RealV1Order

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
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_order())
