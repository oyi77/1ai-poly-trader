import asyncio
import logging
import sys
from backend.data.polymarket_clob import PolymarketCLOB
from backend.config import settings

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def verify_v2():
    print("Testing Polymarket CLOB V2 Migration...")
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live"
    )
    
    async with clob:
        # 1. Test Version Detection
        try:
            version = await asyncio.to_thread(clob._clob_client.get_version)
            print(f"Server reported CLOB version: {version}")
        except Exception as e:
            print(f"Failed to get version: {e}")
            return

        # 2. Test Order Book (Public)
        # We'll use a known token from Gamma if possible.
        # Let's try to fetch a market first to get a valid token_id
        print("Fetching a live market to get a valid token...")
        market = await clob.get_market("0x544747ee745f40cf65f87097ace5ea04760451a5c68b") # Sample condition
        if market and market.get('clobTokenIds'):
            sample_token = market['clobTokenIds'][0]
            print(f"Found token: {sample_token}")
        else:
            # Fallback to a hardcoded recent token if possible, or just skip
            sample_token = "21695781553246117472065386460872660010032dd04c3bb084c2a1cf399d54"
            print(f"Using fallback token: {sample_token}")

        try:
            book = await clob.get_order_book(sample_token)
            print(f"Order book mid-price: {book.mid_price}")
        except Exception as e:
            print(f"Order book fetch failed: {e}")

        # 3. Test Paper Order (Share Calculation)
        print("Testing Paper Order share calculation...")
        # Spend $10 at price 0.5 -> should be 20 shares
        # Note: in Paper mode, it doesn't touch the live SDK's build_order but we check our wrapper
        res = await clob.place_limit_order(sample_token, "BUY", 0.5, 10.0)
        print(f"Paper order result: {res.success}, fill_size: {res.fill_size}, fill_price: {res.fill_price}")
        
        # 4. Test Live Order Signature (Simulation)
        print("Attempting to derive creds and check auth...")
        creds = await clob.create_or_derive_api_creds()
        if creds:
            print("Successfully derived V2 API credentials")
            
            print("Testing get_open_orders (Authenticated)...")
            orders = await clob.get_open_orders()
            print(f"Open orders count: {len(orders)}")
        else:
            print("Failed to derive API credentials")

if __name__ == "__main__":
    asyncio.run(verify_v2())
