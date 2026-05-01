import asyncio
import logging
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
from py_clob_client.order_builder.builder import OrderBuilder
from py_order_utils.builders.order_builder import OrderBuilder as UtilsOrderBuilder

logging.basicConfig(level=logging.INFO)

# Monkey-patch to force the other exchange address
NEG_RISK_EXCHANGE = "0xC5d563486406039ff89a4444830FCF274983e29a"

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
            
            # We'll manually override the neg_risk check to True to force the other exchange
            # Or we can patch get_contract_config
            import py_clob_client.config as config
            original_get_config = config.get_contract_config
            
            def patched_get_config(chain_id, neg_risk=False):
                print(f"FORCING neg_risk=True for exchange address")
                return original_get_config(chain_id, neg_risk=True)
            
            config.get_contract_config = patched_get_config
            
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
