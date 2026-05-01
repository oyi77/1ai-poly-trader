import os
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()
pk = os.getenv("POLYMARKET_PRIVATE_KEY")
if pk:
    acc = Account.from_key(pk)
    print(f"Private key address: {acc.address}")
else:
    print("No POLYMARKET_PRIVATE_KEY found")
