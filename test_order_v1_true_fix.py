import asyncio
import logging
import json
import sys
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
from py_clob_client.order_builder.builder import OrderBuilder
from py_order_utils.model import OrderData
import py_order_utils.model.order as order_mod
from poly_eip712_structs import Address, EIP712Struct, Uint

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Redefine Order WITHOUT signer field (V1 format)
class V1Order(EIP712Struct):
    salt = Uint(256)
    maker = Address()
    # signer = Address() # REMOVED
    taker = Address()
    tokenId = Uint(256)
    makerAmount = Uint(256)
    takerAmount = Uint(256)
    expiration = Uint(256)
    nonce = Uint(256)
    feeRateBps = Uint(256)
    side = Uint(8)
    signatureType = Uint(8)

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
            "signatureType": self["signatureType"],
        }

# Redefine SignedOrder to use V1Order
from py_order_utils.model.order import SignedOrder as OriginalSignedOrder

class V1SignedOrder:
    def __init__(self, order, signature):
        self.order = order
        self.signature = signature

    def dict(self):
        d = self.order.dict()
        d["signature"] = self.signature
        if d["side"] == 0:
            d["side"] = "BUY"
        else:
            d["side"] = "SELL"
        d["expiration"] = str(d["expiration"])
        d["nonce"] = str(d["nonce"])
        d["feeRateBps"] = str(d["feeRateBps"])
        d["makerAmount"] = str(d["makerAmount"])
        d["takerAmount"] = str(d["takerAmount"])
        d["tokenId"] = str(d["tokenId"])
        return d

# Patch OrderBuilder to use V1Order and V1SignedOrder
def v1_patched_create_order(self, order_args, options):
    from py_clob_client.order_builder.builder import ROUNDING_CONFIG, UtilsOrderBuilder, UtilsSigner, get_contract_config
    from py_order_utils.builders.order_builder import OrderBuilder as UtilsOrderBuilder
    
    side, maker_amount, taker_amount = self.get_order_amounts(
        order_args.side,
        order_args.size,
        order_args.price,
        ROUNDING_CONFIG[options.tick_size],
    )

    # Note: We can't use the original UtilsOrderBuilder easily if it's hardcoded to the Original Order class.
    # We might need to manually sign.
    
    # Actually, let's see if UtilsOrderBuilder uses the class from order_mod.Order
    # If we patch order_mod.Order, it might work!
    
    return original_create_order(self, order_args, options)

# LET'S TRY THE SIMPLEST MONKEY PATCH: Replace the Order class in the module
order_mod.Order = V1Order

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
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    # We need to save the original before patching if we want to revert, but this is a script.
    asyncio.run(test_order())
