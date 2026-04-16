"""
Polymarket CLOB execution client.

Uses httpx.AsyncClient for read-only queries (shared connection pool).
Delegates order creation/placement/cancellation to py_clob_client.ClobClient,
which handles EIP-712 signing, L2 HMAC auth, and tick-size resolution internally.

Auth: EIP-712 L1 (derive API keys) + HMAC-SHA256 L2 (per-request headers).
All order sizes in USDC. All prices in [0.01, 0.99].
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    ApiCreds,
    OrderArgs,
    OrderType,
    BalanceAllowanceParams,
    AssetType,
)

from backend.core.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger("trading_bot")

clob_breaker = CircuitBreaker("polymarket_clob")

CLOB_HOST = "https://clob.polymarket.com"  # Polymarket has a single CLOB API; no testnet CLOB exists
GAMMA_HOST = "https://gamma-api.polymarket.com"
DATA_HOST = "https://data-api.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet — Builder Program and all trading run on mainnet

# Polymarket minimum order size
MIN_ORDER_USDC = 5.0


# Keys currently being processed (in-flight guard against concurrent duplicate calls)
_inflight_keys: set[str] = set()
_inflight_lock = asyncio.Lock()


async def _check_and_claim_idempotency(key: str) -> bool:
    """
    Return True (duplicate) if key is already in-flight or in the DB.
    Claims the key in the in-flight set atomically to prevent concurrent duplicates.
    Caller must release via _release_idempotency_key() after the order is recorded.
    """
    async with _inflight_lock:
        if key in _inflight_keys:
            return True
        _inflight_keys.add(key)

    # Check DB for cross-process/restart duplicates
    from backend.models.database import SessionLocal, Trade

    db = SessionLocal()
    try:
        existing = db.query(Trade).filter(Trade.clob_idempotency_key == key).first()
        if existing is not None:
            async with _inflight_lock:
                _inflight_keys.discard(key)
            return True
        return False
    finally:
        db.close()


def _release_idempotency_key(key: str) -> None:
    """Remove key from in-flight set after order is recorded (or failed)."""
    _inflight_keys.discard(key)


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    fill_price: Optional[float] = None
    fill_size: Optional[float] = None
    idempotency_key: Optional[str] = None


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
        simulation: Optional[
            bool
        ] = None,  # backward-compat: simulation=True -> mode="paper"
        builder_api_key: Optional[str] = None,
        builder_secret: Optional[str] = None,
        builder_passphrase: Optional[str] = None,
        builder_address: Optional[str] = None,
        signature_type: int = 0,
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
        self.builder_api_key = builder_api_key
        self.builder_secret = builder_secret
        self.builder_passphrase = builder_passphrase
        self.builder_address = builder_address
        self.signature_type = signature_type

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
            builder_config = None
            if builder_api_key and builder_secret and builder_passphrase:
                try:
                    from py_builder_signing_sdk.config import (
                        BuilderConfig,
                        BuilderApiKeyCreds,
                    )

                    builder_config = BuilderConfig(
                        local_builder_creds=BuilderApiKeyCreds(
                            key=builder_api_key,
                            secret=builder_secret,
                            passphrase=builder_passphrase,
                        )
                    )
                    logger.info(
                        "[polymarket_clob.__init__] Builder Program credentials loaded"
                    )
                except ImportError:
                    logger.warning(
                        "[polymarket_clob.__init__] py_builder_signing_sdk not installed — "
                        "Builder Program auth unavailable. Install with: "
                        "pip install py-builder-signing-sdk"
                    )
            try:
                self._clob_client = ClobClient(
                    host=self._clob_host,
                    chain_id=self._chain_id,
                    key=private_key,
                    creds=creds,
                    signature_type=signature_type,
                    builder_config=builder_config,
                    funder=builder_address if builder_address else None,
                )
            except Exception as e:
                logger.warning(
                    f"[polymarket_clob.__init__] {type(e).__name__}: Failed to initialise ClobClient: {e}",
                    exc_info=True,
                )

    @property
    def simulation(self) -> bool:
        """Backward-compat: True when not in live mode."""
        return self.mode != "live"

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"

    @property
    def _clob_host(self) -> str:
        return CLOB_HOST

    @property
    def _chain_id(self) -> int:
        return CHAIN_ID

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

    def _l2_headers(self, method: str, request_path: str, body: str = "") -> dict:
        """Generate Polymarket L2 HMAC auth headers.

        Raises ValueError if API credentials are not set.
        """
        import hashlib
        import hmac
        import time

        if not self.api_key:
            raise ValueError("api_key required for L2 auth headers")
        if not self.api_secret:
            raise ValueError("api_secret required for L2 auth headers")
        if not self.api_passphrase:
            raise ValueError("api_passphrase required for L2 auth headers")

        timestamp = str(int(time.time()))
        message = timestamp + method.upper() + request_path + (body or "")
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        headers = {
            "POLY_TIMESTAMP": timestamp,
            "POLY_SIGNATURE": signature,
            "POLY_API_KEY": self.api_key,
            "POLY_PASSPHRASE": self.api_passphrase,
        }
        if self._account:
            headers["POLY_ADDRESS"] = self._account.address
        return headers

    # =========================================================================
    # Public read-only endpoints (no auth)
    # =========================================================================

    async def get_order_book(self, token_id: str) -> OrderBook:
        """Fetch live order book for a token."""
        from backend.data.orderbook_cache import get_orderbook_cache

        cache = get_orderbook_cache()
        cached = await cache.get(token_id)

        if cached:
            logger.debug(
                f"Using cached orderbook for {token_id} (age: {cached.age_seconds:.1f}s)"
            )
            return OrderBook(
                token_id=token_id,
                bids=cached.bids,
                asks=cached.asks,
                mid_price=cached.mid_price,
            )

        async def _fetch_book():
            resp = await self._http.get(
                f"{self._clob_host}/book", params={"token_id": token_id}
            )
            resp.raise_for_status()
            data = resp.json()

            bids = sorted(
                data.get("bids", []), key=lambda x: float(x["price"]), reverse=True
            )
            asks = sorted(data.get("asks", []), key=lambda x: float(x["price"]))

            mid = 0.5
            if bids and asks:
                mid = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2
            elif bids:
                mid = float(bids[0]["price"])
            elif asks:
                mid = float(asks[0]["price"])

            return OrderBook(token_id=token_id, bids=bids, asks=asks, mid_price=mid)

        return await clob_breaker.call(_fetch_book)

    async def get_mid_price(self, token_id: str) -> float:
        """Get mid-price for a token (fast, single endpoint)."""
        from backend.data.orderbook_cache import get_orderbook_cache

        cache = get_orderbook_cache()
        cached_price = await cache.get_mid_price(token_id)

        if cached_price is not None:
            logger.debug(f"Using cached mid price for {token_id}: {cached_price:.4f}")
            return cached_price

        try:
            resp = await self._http.get(
                f"{self._clob_host}/midpoint", params={"token_id": token_id}
            )
            resp.raise_for_status()
            return float(resp.json().get("mid", 0.5))
        except Exception as e:
            logger.debug(
                f"[polymarket_clob.get_mid_price] {type(e).__name__}: midpoint endpoint failed, falling back to order book: {e}",
                exc_info=True,
            )
            book = await self.get_order_book(token_id)
            return book.mid_price

    async def get_market(self, condition_id: str) -> Optional[dict]:
        """Get market data from Gamma API."""
        try:
            resp = await self._http.get(
                f"{GAMMA_HOST}/markets", params={"conditionId": condition_id}
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else None
        except Exception as e:
            logger.warning(
                f"[polymarket_clob.get_market] {type(e).__name__}: Failed to fetch market {condition_id}: {e}",
                exc_info=True,
            )
            return None

    async def get_leaderboard(self, window: str = "30d") -> list[dict]:
        """Get Polymarket trader leaderboard."""
        resp = await self._http.get(
            f"{DATA_HOST}/leaderboard", params={"window": window}
        )
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
            creds = await asyncio.to_thread(
                self._clob_client.create_or_derive_api_creds
            )
            if creds:
                # Store and upgrade the client to L2
                self.api_key = creds.api_key
                self.api_secret = creds.api_secret
                self.api_passphrase = creds.api_passphrase
                self._clob_client.set_api_creds(creds)
                logger.info(f"API credentials derived for {self._account.address}")
            return creds
        except Exception as e:
            logger.error(
                f"[polymarket_clob.create_or_derive_api_creds] {type(e).__name__}: Failed to derive API credentials: {e}",
                exc_info=True,
            )
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
            return OrderResult(
                success=False, error=f"Size ${size:.2f} below minimum ${MIN_ORDER_USDC}"
            )

        # Fail fast for live/testnet mode without credentials (before touching the DB)
        if not self.is_paper:
            if not self._clob_client:
                return OrderResult(
                    success=False,
                    error="ClobClient not initialised — private_key required",
                )
            if not self._clob_client.creds:
                return OrderResult(
                    success=False,
                    error="API credentials required — call create_or_derive_api_creds() first",
                )

        # Deterministic key: same params within a 5-min window = same key → deduplicated.
        bucket = int(time.time()) // 300
        raw = f"{token_id}:{side}:{price:.4f}:{size:.4f}:{bucket}"
        idempotency_key = hashlib.sha256(raw.encode()).hexdigest()[:32]
        if await _check_and_claim_idempotency(idempotency_key):
            logger.warning(
                f"Duplicate order detected (key={idempotency_key}), skipping"
            )
            return OrderResult(
                success=False,
                error="Duplicate order: same params already placed this window",
            )
        logger.info(
            f"Order idempotency_key={idempotency_key} | {side} {size} @ {price} token={token_id[:16]}..."
        )

        if self.is_paper:
            # Paper trade: simulate fill at current mid-price
            try:
                mid = await self.get_mid_price(token_id)
            except Exception as e:
                logger.debug(
                    f"[polymarket_clob.place_limit_order] {type(e).__name__}: mid-price fetch failed, using limit price: {e}",
                    exc_info=True,
                )
                mid = price
            logger.info(
                f"[PAPER] {side} {size:.2f} USDC @ {price:.3f} "
                f"(mid={mid:.3f}) token={token_id[:16]}..."
            )
            result = OrderResult(
                success=True,
                order_id=f"paper_{int(time.time())}",
                fill_price=mid,
                fill_size=size,
                idempotency_key=idempotency_key,
            )
            _release_idempotency_key(idempotency_key)
            return result

        # Live/testnet mode — use py-clob-client
        if not self._clob_client:
            _release_idempotency_key(idempotency_key)
            return OrderResult(
                success=False, error="ClobClient not initialised — private_key required"
            )
        if not self._clob_client.creds:
            _release_idempotency_key(idempotency_key)
            return OrderResult(
                success=False,
                error="API credentials required — call create_or_derive_api_creds() first",
            )

        if clob_breaker.state == "OPEN":
            logger.warning("CLOB circuit OPEN, rejecting order placement")
            _release_idempotency_key(idempotency_key)
            return OrderResult(
                success=False, error="Circuit breaker OPEN for polymarket_clob"
            )

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
            resp = await asyncio.to_thread(
                self._clob_client.post_order, signed_order, "GTC"
            )

            order_id = (
                resp.get("orderID", resp.get("id", "unknown"))
                if isinstance(resp, dict)
                else str(resp)
            )
            logger.info(
                f"{mode_label} Order placed: {order_id} | {side} {size} @ {price}"
            )
            await clob_breaker._on_success()
            return OrderResult(success=True, order_id=order_id)

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"[polymarket_clob.place_limit_order] {type(e).__name__}: Order failed: {error_msg}",
                exc_info=True,
            )
            await clob_breaker._on_failure()
            return OrderResult(success=False, error=error_msg)
        finally:
            # Always release in-flight guard so same params can be retried later
            _release_idempotency_key(idempotency_key)

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
            logger.error(
                f"[polymarket_clob.cancel_order] {type(e).__name__}: Cancel failed: {e}",
                exc_info=True,
            )
            return False

    async def get_open_orders(self) -> list[dict]:
        """Get all open orders for this account. Delegates to py-clob-client."""
        if self.is_paper or not self._clob_client or not self._clob_client.creds:
            return []
        try:
            return await asyncio.to_thread(self._clob_client.get_orders)
        except Exception as e:
            logger.error(
                f"[polymarket_clob.get_open_orders] {type(e).__name__}: Failed to get open orders: {e}",
                exc_info=True,
            )
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
            logger.error(
                f"[polymarket_clob.cancel_all_orders] {type(e).__name__}: Failed to cancel all orders: {e}",
                exc_info=True,
            )
            return False

    async def get_wallet_balance(self) -> dict:
        """
        Fetch wallet balance from Polymarket.

        Returns:
            dict: {
                "usdc_balance": float,
                "token_balances": dict,  # token_id -> balance
                "error": str | None
            }
        """
        if self.is_paper or not self._clob_client or not self._clob_client.creds:
            return {
                "usdc_balance": 0.0,
                "token_balances": {},
                "error": "Not in live/testnet mode or not authenticated",
            }

        try:
            # Fetch collateral balance (USDC) with correct signature_type for proxy wallets
            params = BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=self.signature_type if self.signature_type else None,
            )
            resp = await asyncio.to_thread(
                self._clob_client.get_balance_allowance, params
            )

            if resp and isinstance(resp, dict):
                usdc_balance = (
                    float(resp.get("balance", 0)) / 1e6
                )  # Convert from 6 decimals
                return {
                    "usdc_balance": usdc_balance,
                    "token_balances": resp.get("tokenBalances", {}),
                    "error": None,
                }
            else:
                return {
                    "usdc_balance": 0.0,
                    "token_balances": {},
                    "error": "Invalid response from balance endpoint",
                }
        except Exception as e:
            logger.error(
                f"[polymarket_clob.get_wallet_balance] {type(e).__name__}: Failed to fetch wallet balance: {e}",
                exc_info=True,
            )
            return {"usdc_balance": 0.0, "token_balances": {}, "error": str(e)}


# =========================================================================
# Convenience: get clob client from settings
# =========================================================================


def clob_from_settings(mode: str = None) -> PolymarketCLOB:
    """Create PolymarketCLOB from app settings."""
    from backend.config import settings

    return PolymarketCLOB(
        private_key=settings.POLYMARKET_PRIVATE_KEY,
        api_key=settings.POLYMARKET_API_KEY,
        api_secret=settings.POLYMARKET_API_SECRET,
        api_passphrase=settings.POLYMARKET_API_PASSPHRASE,
        mode=mode or settings.TRADING_MODE,
        builder_api_key=settings.POLYMARKET_BUILDER_API_KEY,
        builder_secret=settings.POLYMARKET_BUILDER_SECRET,
        builder_passphrase=settings.POLYMARKET_BUILDER_PASSPHRASE,
        builder_address=settings.POLYMARKET_BUILDER_ADDRESS,
        signature_type=settings.POLYMARKET_SIGNATURE_TYPE,
    )
