"""Test suite for AsterProvider."""

import os
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock

from backend.markets.order_types import (
    NormalizedOrder,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionSide,
    VenueCapability,
)


# Valid 32-byte hex private key for AsterClient's EthAccount.from_key()
_VALID_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


@pytest.fixture
def provider():
    with patch.dict(os.environ, {"WALLET_PRIVATE_KEY": _VALID_KEY, "ASTER_PRIVATE_KEY": _VALID_KEY}, clear=False):
        with patch("backend.clients.aster_client.AsterClient.__init__", return_value=None):
            from backend.markets.providers.aster_provider import AsterProvider
            p = AsterProvider(paper_mode=True)
            p._client = MagicMock()
            return p


def test_manifest(provider):
    m = provider.manifest()
    assert m.name == "aster"
    assert m.is_live_venue is True
    assert VenueCapability.LIMIT_ORDERS in m.capabilities
    assert VenueCapability.SHORT_SELLING in m.capabilities
    assert "WALLET_PRIVATE_KEY" in m.required_env_vars


@pytest.mark.asyncio
async def test_place_order_paper_mode(provider):
    order = NormalizedOrder(
        market_id="ETHUSDT", side=OrderSide.BUY,
        order_type=OrderType.LIMIT, size=Decimal("1"),
        price=Decimal("3500"),
    )
    result = await provider.place_order(order)
    assert result.status == OrderStatus.FILLED
    assert result.filled_size == Decimal("1")
    assert result.venue_order_id.startswith("paper_ast_")


@pytest.mark.asyncio
async def test_place_order_live_success(provider):
    provider._paper_mode = False
    mock_client = AsyncMock()
    mock_client.place_order = AsyncMock(return_value={
        "id": "ast_123", "orderId": "ast_123",
        "filled": "0.5", "average": "3500.50",
        "fee": {"cost": "0.175"},
    })
    provider._client = mock_client
    order = NormalizedOrder(
        market_id="ETHUSDT", side=OrderSide.BUY,
        order_type=OrderType.MARKET, size=Decimal("1"),
    )
    result = await provider.place_order(order)
    assert result.venue_order_id == "ast_123"
    assert result.status == OrderStatus.OPEN
    assert result.filled_size == Decimal("0.5")


@pytest.mark.asyncio
async def test_place_order_live_exception(provider):
    provider._paper_mode = False
    mock_client = AsyncMock()
    mock_client.place_order = AsyncMock(side_effect=Exception("insufficient margin"))
    provider._client = mock_client
    order = NormalizedOrder(
        market_id="ETHUSDT", side=OrderSide.BUY,
        order_type=OrderType.MARKET, size=Decimal("1"),
    )
    result = await provider.place_order(order)
    assert result.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_cancel_order(provider):
    mock_client = AsyncMock()
    mock_client.cancel_order = AsyncMock(return_value=True)
    provider._client = mock_client
    result = await provider.cancel_order("ast_123:ETHUSDT")
    assert result is True
    mock_client.cancel_order.assert_called_once_with("ast_123", "ETHUSDT")


@pytest.mark.asyncio
async def test_cancel_order_fails(provider):
    mock_client = AsyncMock()
    mock_client.cancel_order = AsyncMock(side_effect=Exception("not found"))
    provider._client = mock_client
    result = await provider.cancel_order("bad_id")
    assert result is False


@pytest.mark.asyncio
async def test_get_balance(provider):
    mock_client = AsyncMock()
    mock_client.get_balance = AsyncMock(return_value={
        "USDC": {"free": "1000", "total": "1500", "used": "500"}
    })
    provider._client = mock_client
    bal = await provider.get_balance()
    assert bal.venue == "aster"
    assert bal.available_cash == Decimal("1000")
    assert bal.total_equity == Decimal("1500")
    assert bal.reserved_margin == Decimal("500")


@pytest.mark.asyncio
async def test_get_balance_non_dict(provider):
    mock_client = AsyncMock()
    mock_client.get_balance = AsyncMock(return_value={"USDC": "invalid"})
    provider._client = mock_client
    bal = await provider.get_balance()
    assert bal.available_cash == Decimal("0")


@pytest.mark.asyncio
async def test_get_positions(provider):
    mock_client = AsyncMock()
    mock_client.get_positions = AsyncMock(return_value=[
        {"symbol": "ETHUSDT", "contracts": "2.5", "side": "long", "entryPrice": "3500", "markPrice": "3600", "unrealizedPnl": "250"},
        {"symbol": "BTCUSDT", "contracts": "0.1", "side": "short", "entryPrice": "100000", "markPrice": "99000", "unrealizedPnl": "100"},
        {"symbol": "SOLUSDT", "contracts": "0", "side": "long", "entryPrice": "0", "markPrice": "150"},
    ])
    provider._client = mock_client
    positions = await provider.get_positions()
    assert len(positions) == 2
    assert positions[0].market_id == "ETHUSDT"
    assert positions[0].side == PositionSide.LONG
    assert positions[0].size == Decimal("2.5")
    assert positions[1].side == PositionSide.SHORT


@pytest.mark.asyncio
async def test_health_check(provider):
    mock_client = AsyncMock()
    mock_client.health_check = AsyncMock(return_value=True)
    provider._client = mock_client
    assert await provider.health_check() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
