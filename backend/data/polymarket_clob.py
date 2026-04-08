"""
Polymarket CLOB execution client.

Uses httpx.AsyncClient for read-only queries (shared connection pool).
Delegates order creation/placement/cancellation to py_clob_client.ClobClient,
which handles EIP-712 signing, L2 HMAC auth, and tick-size resolution internally.

Auth: EIP-712 L1 (derive API keys) + HMAC-SHA256 L2 (per-request headers).
All order sizes in USDC. All prices in [0.01, 0.99].
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType

logger = logging.getLogger("trading_bot")

CLOB_HOST_MAINNET = "https://clob.polymarket.com"
CLOB_HOST_TESTNET = "https://clob-staging.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
DATA_HOST = "https://data-api.polymarket.com"
CHAIN_ID_MAINNET = 137
CHAIN_ID_AMOY = 80002

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

        # Shared async connection pool for read-only queries
        self._http: Optional[httpx.AsyncClient] = None

        # py-clob-client instance for order operations (sync — wrapped via asyncio.to_thread)
        self._clob_client: Optional[ClobClient] = None
        if private_key:
            creds = None
            if api_key and api_secret and api_passphrase:
                creds = ApiCreds(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=api_passphrase,
                )
            try:
                self._clob_client = ClobClient(
                    host=self._clob_host,
                    chain_id=self._chain_id,
                    key=private_key,
                    creds=creds,
                )
            except Exception as e:
                logger.warning(f"Failed to initialise ClobClient: {e}")

    @property
    def simulation(self) -> bool:
        """Backward-compat: True when not in live mode."""
        return self.mode != "live"

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"

    @property
    def _clob_host(self) -> str:
        # paper uses mainnet host for real price data (no real orders submitted)
        if self.mode in ("live", "paper"):
            return CLOB_HOST_MAINNET
        return CLOB_HOST_TESTNET  # testnet

    @property
    def _chain_id(self) -> int:
        return CHAIN_ID_AMOY if self.mode == "testnet" else CHAIN_ID_MAINNET

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
        resp = await self._http.get(f"{self._clob_host}/book", params={"token_id": token_id})
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
            resp = await self._http.get(f"{self._clob_host}/midpoint", params={"token_id": token_id})
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
    # API credential derivation (via py-clob-client)
    # =========================================================================

    async def create_or_derive_api_creds(self) -> Optional[ApiCreds]:
        """
        Derive or create API credentials from the private key.

        Uses ClobClient.create_or_derive_api_creds() which:
        1. Tries to create a new API key (L1 auth via private key)
        2. Falls back to deriving an existing key if already created

        Returns ApiCreds(api_key, api_secret, api_passphrase) or None on failure.
        """
        if not self._clob_client:
            logger.error("ClobClient not initialised — private_key required")
            return None
        try:
            creds = await asyncio.to_thread(self._clob_client.create_or_derive_api_creds)
            if creds:
                # Store and upgrade the client to L2
                self.api_key = creds.api_key
                self.api_secret = creds.api_secret
                self.api_passphrase = creds.api_passphrase
                self._clob_client.set_api_creds(creds)
                logger.info(f"API credentials derived for {self._account.address}")
            return creds
        except Exception as e:
            logger.error(f"Failed to derive API credentials: {e}")
            return None

    # =========================================================================
    # Authenticated order management (delegated to py-clob-client)
    # =========================================================================

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

        In paper mode: returns a fake success with mid-price fill.
        In live/testnet mode: delegates to py-clob-client for signing and submission.

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

        # Live/testnet mode — use py-clob-client
        if not self._clob_client:
            return OrderResult(success=False, error="ClobClient not initialised — private_key required")
        if not self._clob_client.creds:
            return OrderResult(success=False, error="API credentials required — call create_or_derive_api_creds() first")

        mode_label = "[TESTNET]" if self.mode == "testnet" else "[LIVE]"
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
            )

            # ClobClient.create_order handles tick-size resolution, neg_risk, signing
            signed_order = await asyncio.to_thread(
                self._clob_client.create_order, order_args
            )

            # Post the signed order
            ot = OrderType(order_type)
            resp = await asyncio.to_thread(
                self._clob_client.post_order, signed_order, ot
            )

            order_id = resp.get("orderID", resp.get("id", "unknown")) if isinstance(resp, dict) else str(resp)
            logger.info(f"{mode_label} Order placed: {order_id} | {side} {size} @ {price}")
            return OrderResult(success=True, order_id=order_id)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Order failed: {error_msg}")
            return OrderResult(success=False, error=error_msg)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Delegates to py-clob-client."""
        if self.is_paper:
            logger.info(f"[PAPER] Cancel order {order_id}")
            return True
        if not self._clob_client or not self._clob_client.creds:
            logger.error("Cancel requires ClobClient with API credentials")
            return False
        try:
            resp = await asyncio.to_thread(self._clob_client.cancel, order_id)
            return resp.get("success", False) if isinstance(resp, dict) else bool(resp)
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return False

    async def get_open_orders(self) -> list[dict]:
        """Get all open orders for this account. Delegates to py-clob-client."""
        if self.is_paper or not self._clob_client or not self._clob_client.creds:
            return []
        try:
            return await asyncio.to_thread(self._clob_client.get_orders)
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders. Delegates to py-clob-client."""
        if self.is_paper:
            return True
        if not self._clob_client or not self._clob_client.creds:
            logger.error("Cancel all requires ClobClient with API credentials")
            return False
        try:
            resp = await asyncio.to_thread(self._clob_client.cancel_all)
            logger.info("Cancelled all open orders")
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
