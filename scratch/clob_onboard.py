import asyncio
import os
from dotenv import load_dotenv
from backend.data.polymarket_clob import PolymarketCLOB

async def onboard():
    load_dotenv()
    print("Onboarding Polymarket CLOB...")
    
    # Initialize in live mode
    clob = PolymarketCLOB(
        private_key=os.getenv("POLYMARKET_PRIVATE_KEY"),
        mode="live",
        signature_type=int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0")),
        builder_address=os.getenv("POLYMARKET_BUILDER_ADDRESS")
    )
    
    async with clob:
        if clob._account:
            print(f"Wallet address: {clob._account.address}")
        print("Deriving/Creating API credentials...")
        creds = await clob.create_or_derive_api_creds()
        if creds:
            print("SUCCESS! Derived credentials:")
            print(f"API Key: {creds.api_key}")
            print(f"API Secret: {creds.api_secret}")
            print(f"API Passphrase: {creds.api_passphrase}")
            
            print("\nUpdating .env file...")
            # We don't strictly need to update .env if the bot derives them on startup,
            # but it's good for debugging.
        else:
            print("FAILED to derive credentials.")

if __name__ == "__main__":
    asyncio.run(onboard())
