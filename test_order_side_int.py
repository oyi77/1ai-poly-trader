import asyncio
import logging
import json
import sys
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
import py_order_utils.model.order as order_mod

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Monkey-patch SignedOrder.dict to KEEP side as int
original_signed_order_dict = order_mod.SignedOrder.dict

def patched_signed_order_dict(self):
    d = self.order.dict()
    d["signature"] = self.signature
    # DO NOT convert side to string!
    # d["side"] = "BUY" if d["side"] == 0 else "SELL" 
    
    # Still convert other fields to strings as the server likely expects them as strings
    d["expiration"] = str(d["expiration"])
    d["nonce"] = str(d["nonce"])
    d["feeRateBps"] = str(d["feeRateBps"])
    d["makerAmount"] = str(d["makerAmount"])
    d["takerAmount"] = str(d["takerAmount"])
    d["tokenId"] = str(d["tokenId"])
    return d

order_mod.SignedOrder.dict = patched_signed_order_dict

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
