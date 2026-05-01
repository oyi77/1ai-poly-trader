
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from backend.data.polymarket_clob import clob_breaker
from backend.core.circuit_breaker_pybreaker import polymarket_breaker, db_breaker

async def check():
    print(f"polymarket_clob (custom) state: {clob_breaker._state}")
    print(f"polymarket_clob failure count: {clob_breaker.failure_count}")
    
    print(f"polymarket_api (pybreaker) state: {polymarket_breaker.current_state}")
    print(f"database (pybreaker) state: {db_breaker.current_state}")

if __name__ == "__main__":
    asyncio.run(check())
