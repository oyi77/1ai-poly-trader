import pytest
from unittest.mock import patch, AsyncMock
from backend.core.trade_forensics import classify_trade_role, classify_trade_role_sync, TradeRole

@pytest.mark.asyncio
async def test_paper_mode_market_order():
    """In paper mode, a market order should always be classified as taker."""
    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="paper",
        clob_order_id=None,
        price=0.50,
        size=10.0,
        direction="up",
        decision={"order_type": "market"}
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0

@pytest.mark.asyncio
async def test_paper_mode_limit_order_maker():
    """In paper mode, a limit order that does not cross the spread should be a maker."""
    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="paper",
        clob_order_id=None,
        price=0.50,
        size=10.0,
        direction="up",
        decision={
            "order_type": "limit",
            "best_ask": 0.52,
            "best_bid": 0.48
        }
    )
    assert role == TradeRole.MAKER.value
    assert maker_size == 10.0
    assert taker_size == 0.0

@pytest.mark.asyncio
async def test_paper_mode_limit_order_taker_crossing():
    """In paper mode, a limit buy order crossing the best ask is a taker."""
    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="paper",
        clob_order_id=None,
        price=0.53,
        size=10.0,
        direction="up",
        decision={
            "order_type": "limit",
            "best_ask": 0.52,
            "best_bid": 0.48
        }
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0

@pytest.mark.asyncio
async def test_paper_mode_limit_order_taker_crossing_sell():
    """In paper mode, a limit sell order crossing the best bid is a taker."""
    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="paper",
        clob_order_id=None,
        price=0.47,
        size=10.0,
        direction="down",
        decision={
            "order_type": "limit",
            "best_ask": 0.52,
            "best_bid": 0.48
        }
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0

@pytest.mark.asyncio
async def test_live_mode_fallback_market():
    """In live mode, if order ID is present but lookup fails, market orders fall back to taker."""
    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="live",
        clob_order_id="order-123",
        price=0.50,
        size=10.0,
        direction="up",
        decision={"order_type": "market"}
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0

@pytest.mark.asyncio
async def test_live_mode_fallback_limit_with_spread():
    """In live mode, if lookup fails, limit orders check spread. Crossing is taker."""
    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="live",
        clob_order_id="order-123",
        price=0.55,
        size=10.0,
        direction="up",
        decision={
            "order_type": "limit",
            "best_ask": 0.53,
            "best_bid": 0.49
        }
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0

@pytest.mark.asyncio
@patch("backend.data.polymarket_clob.PolymarketCLOB")
@patch("backend.config.settings")
async def test_live_mode_polymarket_fills_api_maker(mock_settings, mock_client_class):
    """If Polymarket fills API reports order is maker, classify as maker."""
    mock_settings.PROXY_WALLET_ADDRESS = "0xwallet"
    mock_client = AsyncMock()
    mock_client.get_trader_trades.return_value = [
        {"orderID": "order-123", "maker": True}
    ]
    mock_client_class.return_value = mock_client

    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="live",
        clob_order_id="order-123",
        price=0.50,
        size=10.0,
        direction="up",
        decision={}
    )
    assert role == TradeRole.MAKER.value
    assert maker_size == 10.0
    assert taker_size == 0.0

@pytest.mark.asyncio
@patch("backend.data.polymarket_clob.PolymarketCLOB")
@patch("backend.config.settings")
async def test_live_mode_polymarket_fills_api_taker(mock_settings, mock_client_class):
    """If Polymarket fills API reports order is not maker, classify as taker."""
    mock_settings.PROXY_WALLET_ADDRESS = "0xwallet"
    mock_client = AsyncMock()
    mock_client.get_trader_trades.return_value = [
        {"orderID": "order-123", "maker": False}
    ]
    mock_client_class.return_value = mock_client

    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="live",
        clob_order_id="order-123",
        price=0.50,
        size=10.0,
        direction="up",
        decision={}
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0

@pytest.mark.asyncio
@patch("backend.data.polymarket_clob.PolymarketCLOB")
@patch("backend.config.settings")
async def test_live_mode_polymarket_fills_api_failure_fallback(mock_settings, mock_client_class):
    """If fills API call throws an error, fallback to heuristics gracefully."""
    mock_settings.PROXY_WALLET_ADDRESS = "0xwallet"
    mock_client = AsyncMock()
    mock_client.get_trader_trades.side_effect = Exception("API offline")
    mock_client_class.return_value = mock_client

    # Fallback with no spread details should default limit to maker
    role, maker_size, taker_size = await classify_trade_role(
        platform="polymarket",
        mode="live",
        clob_order_id="order-123",
        price=0.50,
        size=10.0,
        direction="up",
        decision={"order_type": "limit"}
    )
    assert role == TradeRole.MAKER.value
    assert maker_size == 10.0
    assert taker_size == 0.0

def test_sync_wrapper_outside_loop():
    """Calling classify_trade_role_sync from a normal synchronous context."""
    role, maker_size, taker_size = classify_trade_role_sync(
        platform="polymarket",
        mode="paper",
        clob_order_id=None,
        price=0.50,
        size=10.0,
        direction="up",
        decision={"order_type": "market"}
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0

@pytest.mark.asyncio
async def test_sync_wrapper_inside_running_loop():
    """Calling classify_trade_role_sync when an event loop is running (e.g. in async test)."""
    # This triggers the threading fallback path in classify_trade_role_sync to prevent RuntimeError.
    role, maker_size, taker_size = classify_trade_role_sync(
        platform="polymarket",
        mode="paper",
        clob_order_id=None,
        price=0.50,
        size=10.0,
        direction="up",
        decision={"order_type": "market"}
    )
    assert role == TradeRole.TAKER.value
    assert taker_size == 10.0
    assert maker_size == 0.0
