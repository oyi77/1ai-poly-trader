import asyncio
import logging
import json
import sys
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
from py_clob_client.order_builder.builder import OrderBuilder
from py_order_utils.model import OrderData

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("debug_logger")

# Monkey-patch OrderBuilder.create_order to REMOVE signer if it matches maker
original_create_order = OrderBuilder.create_order

def patched_create_order(self, order_args, options):
    print("PATCHING OrderBuilder.create_order to remove signer field if it matches maker")
    signed_order = original_create_order(self, order_args, options)
    
    # We can't easily change the SignedOrder after it's built because it's already signed.
    # We need to change the OrderData BEFORE build_signed_order is called.
    return signed_order

# Let's monkey-patch the whole method by copying it and modifying
def deep_patched_create_order(self, order_args, options):
    from py_clob_client.order_builder.builder import ROUNDING_CONFIG, UtilsOrderBuilder, UtilsSigner, get_contract_config
    
    side, maker_amount, taker_amount = self.get_order_amounts(
        order_args.side,
        order_args.size,
        order_args.price,
        ROUNDING_CONFIG[options.tick_size],
    )

    # V1 orders (maker == signer) should NOT have the signer field in the struct for some endpoints
    # Actually, let's try setting signer to None
    data = OrderData(
        maker=self.funder,
        taker=order_args.taker,
        tokenId=order_args.token_id,
        makerAmount=str(maker_amount),
        takerAmount=str(taker_amount),
        side=side,
        feeRateBps=str(order_args.fee_rate_bps),
        nonce=str(order_args.nonce),
        signer=None, # <--- THIS IS THE CHANGE
        expiration=str(order_args.expiration),
        signatureType=self.sig_type,
    )

    contract_config = get_contract_config(
        self.signer.get_chain_id(), options.neg_risk
    )

    order_builder = UtilsOrderBuilder(
        contract_config.exchange,
        self.signer.get_chain_id(),
        UtilsSigner(key=self.signer.private_key),
    )

    return order_builder.build_signed_order(data)

OrderBuilder.create_order = deep_patched_create_order

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
