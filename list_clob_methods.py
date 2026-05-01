import asyncio
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

async def list_methods():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live"
    )
    async with clob:
        try:
            await clob.create_or_derive_api_creds()
            methods = [m for m in dir(clob._clob_client) if not m.startswith("_")]
            print("\n".join(methods))
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(list_methods())
