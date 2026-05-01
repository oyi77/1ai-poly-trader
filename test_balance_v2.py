import asyncio
import httpx
from backend.core.bankroll_reconciliation import get_polymarket_wallet_address

async def get_balance(rpc_url, token_address, wallet_address):
    data = "0x70a08231000000000000000000000000" + wallet_address.lower()[2:]
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": token_address, "data": data}, "latest"],
        "id": 1,
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.post(rpc_url, json=payload)
        if res.status_code == 200 and "result" in res.json():
            hex_val = res.json()["result"]
            if hex_val == "0x" or not hex_val: return 0.0
            return int(hex_val, 16) / 1e6
    return 0.0

async def main():
    wallet = get_polymarket_wallet_address()
    print(f"Wallet: {wallet}")
    rpc = "https://rpc-mainnet.matic.quiknode.pro"
    
    usdc_e = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    usdc_native = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
    
    val_e = await get_balance(rpc, usdc_e, wallet)
    val_native = await get_balance(rpc, usdc_native, wallet)
    
    print(f"USDC.e: {val_e}")
    print(f"USDC Native: {val_native}")

if __name__ == "__main__":
    asyncio.run(main())
