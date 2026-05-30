"""Test suite for OstiumProvider."""

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


@pytest.fixture
def provider():
    with patch.dict(os.environ, {"WALLET_PRIVATE_KEY": "0x" + "aa" * 32}, clear=False):
        with patch("backend.clients.ostium_client.OstiumClient.__init__", return_value=None):
            from backend.markets.providers.ostium_provider import OstiumProvider
            p = OstiumProvider(paper_mode=True)
            p._client = MagicMock()
            return p


def test_manifest(provider):
    m = provider.manifest()
    assert m.name == "ostium"
    assert m.is_live_venue is True
    assert VenueCapability.LIMIT_ORDERS in m.capabilities
    assert VenueCapability.MARKET_ORDERS in m.capabilities
    assert VenueCapability.SHORT_SELLING in m.capabilities
    assert "WALLET_PRIVATE_KEY" in m.required_env_vars


@pytest.mark.asyncio
async def test_place_order_paper_mode(provider):
    order = NormalizedOrder(
        market_id="1", side=OrderSide.BUY,
        order_type=OrderType.LIMIT, size=Decimal("100"),
        price=Decimal("3500"),
    )
    result = await provider.place_order(order)
    assert result.status == OrderStatus.FILLED
    assert result.filled_size == Decimal("100")
    assert result.venue_order_id.startswith("paper_ost_")


@pytest.mark.asyncio
async def test_place_order_live_success(provider):
    provider._paper_mode = False
    mock_client = AsyncMock()
    mock_client.place_order = AsyncMock(return_value={"order_id": "ost_123", "status": "open"})
    provider._client = mock_client
    order = NormalizedOrder(
        market_id="1", side=OrderSide.BUY,
        order_type=OrderType.MARKET, size=Decimal("100"),
        metadata={"leverage": 5},
    )
    result = await provider.place_order(order)
    assert result.venue_order_id == "ost_123"
    assert result.status == OrderStatus.OPEN


@pytest.mark.asyncio
async def test_place_order_live_exception(provider):
    provider._paper_mode = False
    mock_client = AsyncMock()
    mock_client.place_order = AsyncMock(side_effect=Exception("on-chain fail"))
    provider._client = mock_client
    order = NormalizedOrder(
        market_id="1", side=OrderSide.BUY,
        order_type=OrderType.MARKET, size=Decimal("100"),
    )
    result = await provider.place_order(order)
    assert result.status == OrderStatus.REJECTED
    assert "on-chain fail" in result.raw["error"]


@pytest.mark.asyncio
async def test_cancel_order(provider):
    mock_client = AsyncMock()
    mock_client.cancel_order = AsyncMock(return_value=True)
    provider._client = mock_client
    result = await provider.cancel_order("5:0")
    assert result is True
    mock_client.cancel_order.assert_called_once_with(5, 0)


@pytest.mark.asyncio
async def test_cancel_order_fails(provider):
    mock_client = AsyncMock()
    mock_client.cancel_order = AsyncMock(side_effect=Exception("fail"))
    provider._client = mock_client
    result = await provider.cancel_order("5:0")
    assert result is False


@pytest.mark.asyncio
async def test_get_balance(provider):
    mock_client = AsyncMock()
    mock_client.get_balance = AsyncMock(return_value={"balance": "1234.56"})
    provider._client = mock_client
    bal = await provider.get_balance()
    assert bal.venue == "ostium"
    assert bal.available_cash == Decimal("1234.56")


@pytest.mark.asyncio
async def test_get_positions(provider):
    mock_client = AsyncMock()
    mock_client.get_positions = AsyncMock(return_value=[
        {"pairId": 1, "collateral": "500", "direction": True, "entryPrice": "3500", "currentPrice": "3600", "pnl": "50"},
        {"pairId": 2, "collateral": "300", "isLong": False, "open_price": "100000", "currentPrice": "99000", "pnl": "-10"},
        {"pairId": 3, "collateral": "0", "direction": True},
    ])
    provider._client = mock_client
    positions = await provider.get_positions()
    assert len(positions) == 2  # zero-size filtered
    assert positions[0].market_id == "1"
    assert positions[0].side == PositionSide.LONG
    assert positions[0].venue == "ostium"
    assert positions[1].side == PositionSide.SHORT


@pytest.mark.asyncio
async def test_health_check(provider):
    mock_client = AsyncMock()
    mock_client.health_check = AsyncMock(return_value=True)
    provider._client = mock_client
    assert await provider.health_check() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
