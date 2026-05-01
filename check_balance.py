import asyncio
import logging
import sys
from backend.data.polymarket_clob import PolymarketCLOB
from backend.config import settings

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def check_balances():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        builder_address=settings.POLYMARKET_BUILDER_ADDRESS,
        mode="live"
    )
    async with clob:
        # Crucial: derive creds
        await clob.create_or_derive_api_creds()
        
        print("Checking balances for address:", settings.POLYMARKET_BUILDER_ADDRESS or clob._account.address)
        balance = await clob.get_wallet_balance()
        print(f"Total Balance (pUSD + USDC): ${balance.get('usdc_balance', 0):.2f}")
        if balance.get('error'):
            print(f"Error: {balance.get('error')}")

if __name__ == "__main__":
    asyncio.run(check_balances())
