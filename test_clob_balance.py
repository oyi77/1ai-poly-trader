import asyncio
from backend.data.polymarket_clob import clob_from_settings
import logging
logging.basicConfig(level=logging.DEBUG)

async def main():
    clob = clob_from_settings(mode="live")
    async with clob:
        # This will derive the proxy from the API credentials
        await clob.create_or_derive_api_creds()
        print("API Address:", clob.api_key)
        balance = await clob.get_wallet_balance()
        print("CLOB Balance Response:", balance)

if __name__ == "__main__":
    asyncio.run(main())
