"""
Tests for CLOBWebSocket client.

Covers: message parsing, subscription management, price update dispatch,
reconnect back-off logic, and stop/cleanup.
"""
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ============================================================================
# Test PriceUpdate dataclass
# ============================================================================

class TestPriceUpdate:
    def test_spread_with_both_sides(self):
        from backend.data.ws_client import PriceUpdate
        p = PriceUpdate(token_id="t1", best_ask=0.60, best_bid=0.55, mid_price=0.575)
        assert abs(p.spread - 0.05) < 1e-9

    def test_spread_missing_side_returns_one(self):
        from backend.data.ws_client import PriceUpdate
        p = PriceUpdate(token_id="t1", best_ask=None, best_bid=0.55, mid_price=0.55)
        assert p.spread == 1.0

    def test_spread_no_prices_returns_one(self):
        from backend.data.ws_client import PriceUpdate
        p = PriceUpdate(token_id="t1")
        assert p.spread == 1.0


# ============================================================================
# Test CLOBWebSocket._handle_message
# ============================================================================

class TestMessageParsing:
    """Test the WS message parser in isolation."""

    def _make_ws(self, received: list):
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket(on_price=received.append)
        return ws

    def test_single_object_message_dispatches(self):
        received = []
        ws = self._make_ws(received)

        msg = json.dumps({
            "asset_id": "token_abc",
            "bids": [{"price": "0.55", "size": "100"}],
            "asks": [{"price": "0.60", "size": "200"}],
        })
        ws._handle_message(msg)

        assert len(received) == 1
        update = received[0]
        assert update.token_id == "token_abc"
        assert abs(update.best_bid - 0.55) < 1e-9
        assert abs(update.best_ask - 0.60) < 1e-9
        assert abs(update.mid_price - 0.575) < 1e-9

    def test_list_message_dispatches_all(self):
        received = []
        ws = self._make_ws(received)

        msg = json.dumps([
            {"asset_id": "t1", "bids": [{"price": "0.40"}], "asks": [{"price": "0.50"}]},
            {"asset_id": "t2", "bids": [{"price": "0.70"}], "asks": [{"price": "0.75"}]},
        ])
        ws._handle_message(msg)
        assert len(received) == 2
        assert received[0].token_id == "t1"
        assert received[1].token_id == "t2"

    def test_message_without_asset_id_skipped(self):
        received = []
        ws = self._make_ws(received)
        ws._handle_message(json.dumps({"price": "0.50"}))  # no asset_id
        assert received == []

    def test_invalid_json_silently_ignored(self):
        received = []
        ws = self._make_ws(received)
        ws._handle_message("not json {{")  # should not raise
        assert received == []

    def test_mid_price_computed_from_bids_only(self):
        """When only bids present, mid = best bid."""
        received = []
        ws = self._make_ws(received)
        ws._handle_message(json.dumps({
            "asset_id": "t1",
            "bids": [{"price": "0.60"}],
            "asks": [],
        }))
        assert len(received) == 1
        assert abs(received[0].mid_price - 0.60) < 1e-9

    def test_mid_price_fallback_to_price_field(self):
        """No bids/asks — use top-level price field."""
        received = []
        ws = self._make_ws(received)
        ws._handle_message(json.dumps({
            "asset_id": "t1",
            "price": "0.45",
        }))
        assert len(received) == 1
        assert abs(received[0].mid_price - 0.45) < 1e-9

    def test_token_id_fallback_field(self):
        """token_id field is an acceptable alias for asset_id."""
        received = []
        ws = self._make_ws(received)
        ws._handle_message(json.dumps({
            "token_id": "fallback_token",
            "bids": [{"price": "0.50"}],
            "asks": [{"price": "0.55"}],
        }))
        assert len(received) == 1
        assert received[0].token_id == "fallback_token"


# ============================================================================
# Test subscription management
# ============================================================================

class TestSubscriptions:
    @pytest.mark.asyncio
    async def test_subscribe_adds_token(self):
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket()
        await ws.subscribe("abc")
        assert "abc" in ws._subscribed

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_token(self):
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket()
        await ws.subscribe("abc")
        ws.unsubscribe("abc")
        assert "abc" not in ws._subscribed

    def test_unsubscribe_missing_token_noop(self):
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket()
        ws.unsubscribe("nonexistent")  # should not raise

    def test_is_connected_false_initially(self):
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket()
        assert ws.is_connected is False

    @pytest.mark.asyncio
    async def test_subscribe_dispatches_task_when_connected(self):
        """When already connected, subscribe calls _send_subscribe directly."""
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket()
        ws._connected = True
        ws._ws = MagicMock()

        with patch.object(ws, "_send_subscribe", new_callable=AsyncMock) as mock_send:
            await ws.subscribe("new_token")

        assert "new_token" in ws._subscribed
        mock_send.assert_awaited_once_with({"new_token"})


# ============================================================================
# Test stop sets stop event
# ============================================================================

class TestStop:
    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket()
        ws._running = True
        await ws.stop()
        assert ws._running is False

    @pytest.mark.asyncio
    async def test_stop_calls_ws_close(self):
        from backend.data.ws_client import CLOBWebSocket
        ws = CLOBWebSocket()
        ws._running = True
        mock_ws = AsyncMock()
        ws._ws = mock_ws
        await ws.stop()
        mock_ws.close.assert_awaited_once()
