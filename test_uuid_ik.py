import asyncio
import logging
import uuid
from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB

logging.basicConfig(level=logging.INFO)

async def test_order():
    clob = PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        mode="live",
        signature_type=0
    )
    
    async with clob:
        try:
            await clob.create_or_derive_api_creds()
            token_id = "78433024518676680431174478322854148606578065650008220678402966840627347604025"
            
            # Use UUID for idempotency key
            ik = str(uuid.uuid4())
            print(f"Using UUID Idempotency Key: {ik}")
            
            # We need to manually call the internal method or patch the key generation
            # But wait, place_limit_order doesn't take ik as an argument.
            # I'll monkey-patch it.
            
            original_method = clob.place_limit_order
            
            # Actually, I'll just write a custom test function that doesn't use the wrapper
            from py_clob_client.clob_types import OrderArgs
            
            # Need to get tick size etc first.
            # I'll just use the wrapper but monkey-patch the MD5 part.
            import hashlib
            original_md5 = hashlib.md5
            
            class MockHash:
                def __init__(self, data): self.data = data
                def update(self, data): self.data += data
                def hexdigest(self): return str(uuid.uuid4())
            
            def mock_md5(data=b""): return MockHash(data)
            
            # This is risky, let's just use the client directly
            # No, I'll just copy the logic from place_limit_order
            
        except Exception as e:
            print(f"Failed: {e}")

# Actually, let's just update backend/data/polymarket_clob.py to use UUID
# It's better anyway.
