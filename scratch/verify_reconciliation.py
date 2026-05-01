import asyncio
import logging
from backend.core.bankroll_reconciliation import fetch_pm_total_equity

logging.basicConfig(level=logging.INFO)

async def test_reconciliation():
    wallet = "0xAd85C2F3942561AFA448cbbD5811a5f7E2e3C6Bd"
    total_equity = await fetch_pm_total_equity(wallet)
    print(f"\nFinal Total Equity for {wallet}: ${total_equity}")

if __name__ == "__main__":
    asyncio.run(test_reconciliation())
