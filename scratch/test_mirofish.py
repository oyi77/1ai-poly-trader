import asyncio
import logging
from backend.ai.mirofish_client import MiroFishClient

async def test():
    logging.basicConfig(level=logging.INFO)
    print("Testing MiroFish client...")
    client = MiroFishClient()
    print(f"URL: {client.api_url}")
    signals = await client.fetch_signals(market="polymarket")
    print(f"Got {len(signals)} signals")
    for s in signals:
        print(f" - {s.market_id}: prediction={s.prediction}, confidence={s.confidence}")

if __name__ == "__main__":
    asyncio.run(test())
