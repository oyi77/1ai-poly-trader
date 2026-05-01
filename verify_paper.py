import asyncio
import logging
import sys
from backend.data.polymarket_clob import PolymarketCLOB

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def test_paper():
    clob = PolymarketCLOB(mode="paper")
    
    async with clob:
        try:
            token_id = "78433024518676680431174478322854148606578065650008220678402966840627347604025"
            book = await clob.get_order_book(token_id)
            print(f"Paper Order Book Mid: {book.mid_price}")
            
            result = await clob.place_limit_order(
                token_id=token_id,
                price=book.mid_price,
                size=10.0,
                side="BUY"
            )
            print(f"Paper Order Result: {result}")
        except Exception as e:
            print(f"Paper Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_paper())
