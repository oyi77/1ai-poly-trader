import asyncio
import httpx

async def main():
    url = "https://gamma-api.polymarket.com/markets"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch 100 active markets
        r = await client.get(url, params={"active": "true", "limit": 100})
        if r.status_code == 200:
            markets = r.json()
            print("Fetched", len(markets), "active markets")
            for m in markets[:20]:
                print(f"Slug: {m.get('slug')} | Question: {m.get('question')}")
        else:
            print("Status:", r.status_code)

if __name__ == "__main__":
    asyncio.run(main())
