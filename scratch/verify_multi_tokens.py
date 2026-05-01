import asyncio
import httpx

async def check_balances(wallet_address):
    rpc_url = "https://rpc-mainnet.matic.quiknode.pro"
    tokens = {
        "USDC.e": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "USDC Native": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "pUSD": "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb"
    }
    
    results = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, addr in tokens.items():
            data = "0x70a08231000000000000000000000000" + wallet_address.lower()[2:]
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": addr, "data": data}, "latest"],
                "id": 1,
            }
            try:
                res = await client.post(rpc_url, json=payload)
                if res.status_code == 200:
                    hex_val = res.json().get("result", "0x0")
                    if hex_val == "0x" or not hex_val: hex_val = "0x0"
                    balance = int(hex_val, 16) / 1e6
                    results[name] = balance
                else:
                    results[name] = f"Error {res.status_code}"
            except Exception as e:
                results[name] = str(e)
    return results

if __name__ == "__main__":
    wallet = "0xAd85C2F3942561AFA448cbbD5811a5f7E2e3C6Bd"
    res = asyncio.run(check_balances(wallet))
    print(f"Balances for {wallet}:")
    for k, v in res.items():
        print(f"  {k}: {v}")
