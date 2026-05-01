import asyncio
import logging
import json
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB
from py_clob_client.config import get_contract_config
from py_order_utils.builders.order_builder import OrderBuilder as UtilsOrderBuilder
from py_order_utils.signer import Signer as UtilsSigner

logging.basicConfig(level=logging.INFO)

async def debug_domain():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live"
    )
    
    async with clob:
        try:
            token_id = "78433024518676680431174478322854148606578065650008220678402966840627347604025"
            neg_risk = await asyncio.to_thread(clob._clob_client.get_neg_risk, token_id)
            print(f"Token: {token_id}, Neg Risk: {neg_risk}")
            
            contract_config = get_contract_config(137, neg_risk)
            print(f"Exchange Address: {contract_config.exchange}")
            
            utils_builder = UtilsOrderBuilder(
                contract_config.exchange,
                137,
                UtilsSigner(key=settings.POLYMARKET_PRIVATE_KEY)
            )
            
            print(f"Domain Separator: {utils_builder.domain_separator}")
            
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(debug_domain())
