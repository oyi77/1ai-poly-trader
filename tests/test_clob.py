"""
Tests for PolymarketCLOB client.

Focuses on pure-Python logic (OrderBook properties, paper mode, L2 headers)
that can be validated without live network calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


# ============================================================================
# Test OrderBook
# ============================================================================

class TestOrderBook:
    def _make(self, bids=None, asks=None, mid=0.5):
        from backend.data.polymarket_clob import OrderBook
        return OrderBook(token_id="tok", bids=bids or [], asks=asks or [], mid_price=mid)

    def test_best_ask_returns_first_ask(self):
        book = self._make(asks=[{"price": "0.60"}, {"price": "0.65"}])
        assert abs(book.best_ask - 0.60) < 1e-9

    def test_best_bid_returns_first_bid(self):
        book = self._make(bids=[{"price": "0.55"}, {"price": "0.50"}])
        assert abs(book.best_bid - 0.55) < 1e-9

    def test_best_ask_none_when_empty(self):
        book = self._make(asks=[])
        assert book.best_ask is None

    def test_best_bid_none_when_empty(self):
        book = self._make(bids=[])
        assert book.best_bid is None

    def test_spread_with_both_sides(self):
        book = self._make(
            bids=[{"price": "0.55"}],
            asks=[{"price": "0.60"}],
        )
        assert abs(book.spread - 0.05) < 1e-9

    def test_spread_missing_ask_returns_one(self):
        book = self._make(bids=[{"price": "0.55"}], asks=[])
        assert book.spread == 1.0

    def test_spread_missing_bid_returns_one(self):
        book = self._make(bids=[], asks=[{"price": "0.60"}])
        assert book.spread == 1.0


# ============================================================================
# Test OrderResult
# ============================================================================

class TestOrderResult:
    def test_success_result(self):
        from backend.data.polymarket_clob import OrderResult
        r = OrderResult(success=True, order_id="ord123", fill_price=0.55, fill_size=50.0)
        assert r.success
        assert r.order_id == "ord123"
        assert r.error is None

    def test_failure_result(self):
        from backend.data.polymarket_clob import OrderResult
        r = OrderResult(success=False, error="Insufficient funds")
        assert not r.success
        assert r.error == "Insufficient funds"
        assert r.order_id is None


# ============================================================================
# Test PolymarketCLOB paper mode
# ============================================================================

class TestPolymarketCLOBPaper:
    """Paper-mode tests — no real HTTP calls needed for these paths."""

    @pytest.mark.asyncio
    async def test_paper_place_order_returns_success(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            # Mock get_mid_price so we don't need a real network call
            clob.get_mid_price = AsyncMock(return_value=0.58)
            result = await clob.place_limit_order("token1", "BUY", price=0.60, size=25.0)
        assert result.success
        assert result.order_id.startswith("paper_")
        assert abs(result.fill_price - 0.58) < 1e-9
        assert abs(result.fill_size - 25.0) < 1e-9

    @pytest.mark.asyncio
    async def test_paper_place_order_below_minimum_fails(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            result = await clob.place_limit_order("token1", "BUY", price=0.50, size=0.50)
        assert not result.success
        assert "minimum" in result.error.lower()

    @pytest.mark.asyncio
    async def test_paper_cancel_returns_true(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            assert await clob.cancel_order("paper_123") is True

    @pytest.mark.asyncio
    async def test_paper_cancel_all_returns_true(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            assert await clob.cancel_all_orders() is True

    @pytest.mark.asyncio
    async def test_paper_get_open_orders_returns_empty(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            orders = await clob.get_open_orders()
        assert orders == []

    @pytest.mark.asyncio
    async def test_paper_place_order_fills_at_mid_on_price_error(self):
        """If get_mid_price raises, fill falls back to limit price."""
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            clob.get_mid_price = AsyncMock(side_effect=Exception("network error"))
            result = await clob.place_limit_order("token1", "BUY", price=0.45, size=10.0)
        assert result.success
        assert abs(result.fill_price - 0.45) < 1e-9  # fallback to limit price


# ============================================================================
# Test L2 header generation
# ============================================================================

class TestL2Headers:
    def test_headers_include_required_fields(self):
        from backend.data.polymarket_clob import PolymarketCLOB

        pk = "0x" + "a" * 64
        clob = PolymarketCLOB(
            private_key=pk,
            api_key="test_key",
            api_secret="test_secret",
            api_passphrase="test_pass",
            simulation=True,
        )

        headers = clob._l2_headers("POST", "/order", '{"test": true}')
        assert "POLY_ADDRESS" in headers
        assert "POLY_SIGNATURE" in headers
        assert "POLY_TIMESTAMP" in headers
        assert headers["POLY_API_KEY"] == "test_key"
        assert headers["POLY_PASSPHRASE"] == "test_pass"

    def test_headers_raise_without_credentials(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        clob = PolymarketCLOB(simulation=True)  # no api_key
        with pytest.raises(ValueError, match="api_key"):
            clob._l2_headers("GET", "/orders")

    def test_live_place_order_fails_without_credentials(self):
        """Live mode without api_key returns failure immediately."""
        # Construct with no credentials — simulate=False
        from backend.data.polymarket_clob import PolymarketCLOB
        import asyncio

        clob = PolymarketCLOB(simulation=False)
        # Can't use async with cleanly outside a real event loop easily,
        # so call the check directly:
        result = asyncio.get_event_loop().run_until_complete(
            _run_live_without_creds(clob)
        )
        assert not result.success
        assert "private_key" in result.error or "credentials" in result.error


async def _run_live_without_creds(clob):
    import httpx
    clob._http = httpx.AsyncClient()
    try:
        return await clob.place_limit_order("tok", "BUY", 0.5, 10.0)
    finally:
        await clob._http.aclose()


# ============================================================================
# Test HTTP read methods (mocked network)
# ============================================================================

class TestPolymarketCLOBHTTP:
    """Mock _http.get/post to exercise the read-only endpoints."""

    def _mock_resp(self, json_data):
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.raise_for_status = MagicMock()
        return resp

    @pytest.mark.asyncio
    async def test_get_order_book_parses_bids_asks(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp({
                "bids": [{"price": "0.55", "size": "100"}, {"price": "0.50", "size": "200"}],
                "asks": [{"price": "0.60", "size": "150"}, {"price": "0.65", "size": "300"}],
            }))
            book = await clob.get_order_book("token1")

        assert abs(book.best_bid - 0.55) < 1e-9
        assert abs(book.best_ask - 0.60) < 1e-9
        assert abs(book.mid_price - 0.575) < 1e-9

    @pytest.mark.asyncio
    async def test_get_order_book_empty_returns_mid_half(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp({"bids": [], "asks": []}))
            book = await clob.get_order_book("token1")

        assert book.mid_price == 0.5
        assert book.best_bid is None
        assert book.best_ask is None

    @pytest.mark.asyncio
    async def test_get_mid_price_uses_midpoint_endpoint(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp({"mid": "0.72"}))
            mid = await clob.get_mid_price("token1")

        assert abs(mid - 0.72) < 1e-9

    @pytest.mark.asyncio
    async def test_get_mid_price_falls_back_to_order_book(self):
        """If /midpoint raises, get_order_book is used as fallback."""
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            book_resp = self._mock_resp({
                "bids": [{"price": "0.60"}],
                "asks": [{"price": "0.70"}],
            })
            call_count = [0]

            async def get_side_effect(url, **kwargs):
                call_count[0] += 1
                if "midpoint" in str(url):
                    raise Exception("endpoint unavailable")
                return book_resp

            clob._http.get = get_side_effect
            mid = await clob.get_mid_price("token1")

        assert abs(mid - 0.65) < 1e-9  # (0.60 + 0.70) / 2

    @pytest.mark.asyncio
    async def test_get_market_returns_first_result(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        market_data = [{"conditionId": "cond123", "title": "Test Market"}]
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp(market_data))
            result = await clob.get_market("cond123")

        assert result["conditionId"] == "cond123"

    @pytest.mark.asyncio
    async def test_get_market_returns_none_on_empty(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp([]))
            result = await clob.get_market("cond123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_market_returns_none_on_error(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(side_effect=Exception("network error"))
            result = await clob.get_market("cond123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_leaderboard(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        leaderboard = [{"wallet": "0xa", "profit": "5000"}]
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp(leaderboard))
            result = await clob.get_leaderboard()

        assert result == leaderboard

    @pytest.mark.asyncio
    async def test_get_trader_trades(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        trades = [{"transactionHash": "0xtx1", "side": "BUY"}]
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp(trades))
            result = await clob.get_trader_trades("0xwallet", limit=10)

        assert result == trades

    @pytest.mark.asyncio
    async def test_get_trader_positions(self):
        from backend.data.polymarket_clob import PolymarketCLOB
        positions = [{"conditionId": "c1", "size": "100"}]
        async with PolymarketCLOB(simulation=True) as clob:
            clob._http.get = AsyncMock(return_value=self._mock_resp(positions))
            result = await clob.get_trader_positions("0xwallet")

        assert result == positions


# ============================================================================
# Test clob_from_settings convenience factory
# ============================================================================

class TestClobFromSettings:
    def test_creates_paper_clob_by_default(self):
        from backend.data.polymarket_clob import clob_from_settings
        from backend.config import settings
        # Default settings have TRADING_MODE="paper"
        clob = clob_from_settings()
        assert clob.mode == settings.TRADING_MODE
        assert clob.is_paper is True
        assert clob.simulation is True  # backward-compat property
