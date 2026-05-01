import asyncio
from backend.core.bankroll_reconciliation import fetch_pm_total_equity, get_polymarket_wallet_address
import logging
logging.basicConfig(level=logging.DEBUG)

async def main():
    wallet = get_polymarket_wallet_address()
    print("Wallet:", wallet)
    equity = await fetch_pm_total_equity(wallet)
    print("Total Equity:", equity)

if __name__ == "__main__":
    asyncio.run(main())
