"""
Polymarket CLOB execution client.

Uses httpx.AsyncClient directly with a shared connection pool — avoids
py-clob-client's per-request client creation which destroys connection pooling.

Auth: EIP-712 L1 (derive API keys) + HMAC-SHA256 L2 (per-request headers).
All order sizes in USDC. All prices in [0.01, 0.99].
"""
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount

logger = logging.getLogger("trading_bot")

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
DATA_HOST = "https://data-api.polymarket.com"
POLYGON_CHAIN_ID = 137

# Chain IDs
CHAIN_ID_MAINNET = 137
CHAIN_ID_AMOY = 80002

# CTF Exchange contract addresses
CTF_EXCHANGE_MAINNET = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
CTF_EXCHANGE_AMOY = "0xdFE02Eb6733538f8Ea35D585af8DE5958AD99E40"

ORDER_STRUCT_TYPES = {
    "Order": [
        {"name": "salt", "type": "uint256"},
        {"name": "maker", "type": "address"},
        {"name": "signer", "type": "address"},
        {"name": "taker", "type": "address"},
        {"name": "tokenId", "type": "uint256"},
        {"name": "makerAmount", "type": "uint256"},
        {"name": "takerAmount", "type": "uint256"},
        {"name": "expiration", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "feeRateBps", "type": "uint256"},
        {"name": "side", "type": "uint8"},
        {"name": "signatureType", "type": "uint8"},
    ]
}

# Polymarket minimum order size
MIN_ORDER_USDC = 1.0


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    fill_price: Optional[float] = None
    fill_size: Optional[float] = None


@dataclass
class OrderBook:
    token_id: str
    bids: list[dict] = field(default_factory=list)  # [{price, size}]
    asks: list[dict] = field(default_factory=list)
    mid_price: float = 0.5

    @property
    def best_ask(self) -> Optional[float]:
        return float(self.asks[0]["price"]) if self.asks else None

    @property
    def best_bid(self) -> Optional[float]:
        return float(self.bids[0]["price"]) if self.bids else None

    @property
    def spread(self) -> float:
        if self.best_ask and self.best_bid:
            return self.best_ask - self.best_bid
        return 1.0


class PolymarketCLOB:
    """
    Async Polymarket CLOB client with shared httpx connection pool.

    Usage (paper mode — no keys needed):
        async with PolymarketCLOB() as clob:
            book = await clob.get_order_book(token_id)
            mid = book.mid_price

    Usage (live mode):
        async with PolymarketCLOB(private_key=pk, api_key=k, api_secret=s, api_passphrase=p) as clob:
            result = await clob.place_limit_order(token_id, side="BUY", price=0.65, size=50.0)
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
        mode: str = "paper",
        simulation: Optional[bool] = None,  # backward-compat: simulation=True -> mode="paper"
    ):
        # Backward-compat: if simulation kwarg passed, map to mode
        if simulation is not None:
            self.mode = "paper" if simulation else "live"
        else:
            self.mode = mode
        self.private_key = private_key
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase

        self._account: Optional[LocalAccount] = None
        if private_key:
            self._account = Account.from_key(private_key)

        # Shared connection pool — reused across all requests
        self._http: Optional[httpx.AsyncClient] = None

    @property
    def simulation(self) -> bool:
        """Backward-compat: True when not in live mode."""
        return self.mode != "live"

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"

    @property
    def _chain_id(self) -> int:
        return CHAIN_ID_MAINNET if self.mode == "live" else CHAIN_ID_AMOY

    @property
    def _contract_address(self) -> str:
        return CTF_EXCHANGE_MAINNET if self.mode == "live" else CTF_EXCHANGE_AMOY

    async def __aenter__(self):
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            headers={"User-Agent": "PolyEdge/1.0"},
        )
        return self

    async def __aexit__(self, *_):
        if self._http:
            await self._http.aclose()
            self._http = None

    # =========================================================================
    # Public read-only endpoints (no auth)
    # =========================================================================

    async def get_order_book(self, token_id: str) -> OrderBook:
        """Fetch live order book for a token."""
        resp = await self._http.get(f"{CLOB_HOST}/book", params={"token_id": token_id})
        resp.raise_for_status()
        data = resp.json()

        bids = sorted(data.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
        asks = sorted(data.get("asks", []), key=lambda x: float(x["price"]))

        mid = 0.5
        if bids and asks:
            mid = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2
        elif bids:
            mid = float(bids[0]["price"])
        elif asks:
            mid = float(asks[0]["price"])

        return OrderBook(token_id=token_id, bids=bids, asks=asks, mid_price=mid)

    async def get_mid_price(self, token_id: str) -> float:
        """Get mid-price for a token (fast, single endpoint)."""
        try:
            resp = await self._http.get(f"{CLOB_HOST}/midpoint", params={"token_id": token_id})
            resp.raise_for_status()
            return float(resp.json().get("mid", 0.5))
        except Exception:
            book = await self.get_order_book(token_id)
            return book.mid_price

    async def get_market(self, condition_id: str) -> Optional[dict]:
        """Get market data from Gamma API."""
        try:
            resp = await self._http.get(f"{GAMMA_HOST}/markets", params={"conditionId": condition_id})
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else None
        except Exception as e:
            logger.warning(f"Failed to fetch market {condition_id}: {e}")
            return None

    async def get_leaderboard(self, window: str = "30d") -> list[dict]:
        """Get Polymarket trader leaderboard."""
        resp = await self._http.get(f"{DATA_HOST}/leaderboard", params={"window": window})
        resp.raise_for_status()
        return resp.json()

    async def get_trader_trades(self, wallet: str, limit: int = 100) -> list[dict]:
        """Get recent trades for a wallet address."""
        resp = await self._http.get(
            f"{DATA_HOST}/trades",
            params={"user": wallet, "limit": limit, "takerOnly": "true"},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_trader_positions(self, wallet: str) -> list[dict]:
        """Get open positions for a wallet address."""
        resp = await self._http.get(
            f"{DATA_HOST}/positions",
            params={"user": wallet, "sizeThreshold": "1.0"},
        )
        resp.raise_for_status()
        return resp.json()

    # =========================================================================
    # Authenticated order management
    # =========================================================================

    def _sign_order_eip712(self, token_id: str, side: str, price: float, size: float) -> tuple:
        """Sign a CLOB order using EIP-712 typed data signing."""
        import secrets
        from eth_account.messages import encode_typed_data

        side_int = 0 if side == "BUY" else 1
        usdc_amount = int(round(size * 1_000_000))  # 6 decimals
        if side == "BUY":
            maker_amount = usdc_amount
            taker_amount = int(round(size / price * 1_000_000))
        else:
            maker_amount = int(round(size / price * 1_000_000))
            taker_amount = usdc_amount

        if not token_id.isdigit():
            raise ValueError(f"token_id must be a numeric string, got: {token_id!r}. Ensure the CLOB token_id (not condition_id) is used.")
        token_id_int = int(token_id)

        order = {
            "salt": secrets.randbits(128),
            "maker": self._account.address,
            "signer": self._account.address,
            "taker": "0x0000000000000000000000000000000000000000",
            "tokenId": token_id_int,
            "makerAmount": maker_amount,
            "takerAmount": taker_amount,
            "expiration": 0,
            "nonce": 0,
            "feeRateBps": 0,
            "side": side_int,
            "signatureType": 0,
        }

        domain = {
            "name": "Polymarket CTF Exchange",
            "version": "1",
            "chainId": self._chain_id,
            "verifyingContract": self._contract_address,
        }

        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                **ORDER_STRUCT_TYPES,
            },
            "primaryType": "Order",
            "domain": domain,
            "message": order,
        }

        signed = self._account.sign_message(encode_typed_data(full_message=structured_data))
        return order, signed.signature.hex()

    def _l2_headers(self, method: str, path: str, body: str = "") -> dict:
        """
        Generate L2 HMAC-SHA256 authentication headers for CLOB API.
        Required for all order placement and cancellation.
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("api_key and api_secret required for order placement")

        timestamp = str(int(time.time() * 1000))
        message = timestamp + method.upper() + path + (body or "")

        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "POLY_ADDRESS": self._account.address if self._account else "",
            "POLY_SIGNATURE": signature,
            "POLY_TIMESTAMP": timestamp,
            "POLY_API_KEY": self.api_key,
            "POLY_PASSPHRASE": self.api_passphrase or "",
            "Content-Type": "application/json",
        }

    async def place_limit_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: float,
        size: float,
        order_type: str = "GTC",
    ) -> OrderResult:
        """
        Place a limit order on the CLOB.

        In simulation mode: returns a fake success with mid-price fill.
        In live mode: signs and submits to CLOB API.

        price: [0.01, 0.99] — the limit price in USDC per share
        size: USDC amount to spend
        """
        if size < MIN_ORDER_USDC:
            return OrderResult(success=False, error=f"Size ${size:.2f} below minimum ${MIN_ORDER_USDC}")

        if self.is_paper:
            # Paper trade: simulate fill at current mid-price
            try:
                mid = await self.get_mid_price(token_id)
            except Exception:
                mid = price
            logger.info(
                f"[PAPER] {side} {size:.2f} USDC @ {price:.3f} "
                f"(mid={mid:.3f}) token={token_id[:16]}..."
            )
            return OrderResult(
                success=True,
                order_id=f"paper_{int(time.time())}",
                fill_price=mid,
                fill_size=size,
            )

        # Testnet or live mode — sign with EIP-712 and submit
        if not self._account or not self.api_key:
            return OrderResult(success=False, error="Live mode requires private_key and api credentials")

        mode_label = "[TESTNET]" if self.mode == "testnet" else "[LIVE]"
        try:
            order, signature = self._sign_order_eip712(token_id, side, price, size)

            payload = {
                "orderType": order_type,
                "tokenID": token_id,
                "price": str(round(price, 4)),
                "size": str(round(size, 2)),
                "side": side,
                "maker": self._account.address,
                "signer": self._account.address,
                "signature": signature,
                "signatureType": 0,
                "expiration": str(order["expiration"]),
                "nonce": str(order["nonce"]),
                "salt": str(order["salt"]),
                "feeRateBps": str(order["feeRateBps"]),
            }

            body = json.dumps(payload)
            path = "/order"
            headers = self._l2_headers("POST", path, body)

            resp = await self._http.post(f"{CLOB_HOST}{path}", content=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            if data.get("success") or data.get("orderID"):
                order_id = data.get("orderID", data.get("id", "unknown"))
                logger.info(f"{mode_label} Order placed: {order_id} | {side} {size} @ {price}")
                return OrderResult(success=True, order_id=order_id)
            else:
                error = data.get("error", str(data))
                logger.error(f"Order rejected: {error}")
                return OrderResult(success=False, error=error)

        except httpx.HTTPStatusError as e:
            error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error(f"Order failed: {error}")
            return OrderResult(success=False, error=error)
        except Exception as e:
            logger.error(f"Order failed: {e}")
            return OrderResult(success=False, error=str(e))

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if self.is_paper:
            logger.info(f"[PAPER] Cancel order {order_id}")
            return True
        try:
            path = f"/order/{order_id}"
            headers = self._l2_headers("DELETE", path)
            resp = await self._http.delete(f"{CLOB_HOST}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json().get("success", False)
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return False

    async def get_open_orders(self) -> list[dict]:
        """Get all open orders for this account."""
        if self.is_paper or not self.api_key:
            return []
        try:
            path = "/orders"
            headers = self._l2_headers("GET", path)
            resp = await self._http.get(f"{CLOB_HOST}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders. Called on graceful shutdown."""
        if self.is_paper:
            return True
        try:
            path = "/orders/all"
            headers = self._l2_headers("DELETE", path)
            resp = await self._http.delete(f"{CLOB_HOST}{path}", headers=headers)
            resp.raise_for_status()
            count = resp.json().get("canceled", 0)
            logger.info(f"Cancelled {count} open orders")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False


# =========================================================================
# Convenience: get clob client from settings
# =========================================================================

def clob_from_settings() -> PolymarketCLOB:
    """Create PolymarketCLOB from app settings."""
    from backend.config import settings
    return PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        api_key=settings.POLYMARKET_API_KEY,
        api_secret=settings.POLYMARKET_API_SECRET,
        api_passphrase=settings.POLYMARKET_API_PASSPHRASE,
        mode=settings.TRADING_MODE,
    )
