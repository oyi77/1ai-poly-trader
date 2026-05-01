import asyncio
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

async def check_positions():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live"
    )
    async with clob:
        try:
            await clob.create_or_derive_api_creds()
            # ClobClient.get_open_orders() or similar
            # In Version 0.34.6, it's get_open_orders()
            orders = await asyncio.to_thread(clob._clob_client.get_open_orders)
            print(f"Open Orders: {len(orders)}")
            
            # For positions, we might need to check the collateral and assets
            # But the bot's reconciliation logic usually handles this.
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(check_positions())
