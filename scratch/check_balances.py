import os
import httpx
from dotenv import load_dotenv

load_dotenv()
addresses = [
    os.getenv("POLYMARKET_WALLET_ADDRESS"),
    "0xaae484a962a1a20f4542678f920a07589fb665fb"
]

for addr in addresses:
    if not addr: continue
    print(f"Checking address: {addr}")
    # Check balance via Data API
    try:
        resp = httpx.get(f"https://data-api.polymarket.com/value?user={addr}")
        if resp.status_code == 200:
            print(f"  Value: {resp.json()}")
        else:
            print(f"  Failed to get value: {resp.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
