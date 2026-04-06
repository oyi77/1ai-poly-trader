"""Tests for trade settlement logic."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from backend.core.settlement import calculate_pnl, _parse_market_resolution, check_market_settlement
from backend.models.database import Trade


def make_trade(**kwargs) -> Trade:
    """Factory for Trade objects with sensible defaults."""
    t = Trade()
    t.id = kwargs.get("id", 1)
    t.market_ticker = kwargs.get("market_ticker", "test-market")
    t.event_slug = kwargs.get("event_slug", None)
    t.direction = kwargs.get("direction", "up")
    t.entry_price = kwargs.get("entry_price", 0.60)
    t.size = kwargs.get("size", 100.0)
    t.settled = False
    t.signal_id = None
    t.market_type = kwargs.get("market_type", "btc")
    t.trading_mode = kwargs.get("trading_mode", "paper")
    return t


class TestCalculatePnl:
    """Test P&L calculation for all direction/outcome combinations."""

    def test_up_wins(self):
        trade = make_trade(direction="up", entry_price=0.65, size=100.0)
        pnl = calculate_pnl(trade, settlement_value=1.0)
        assert pnl == round(100.0 * (1.0 - 0.65), 2)  # +35.00

    def test_up_loses(self):
        trade = make_trade(direction="up", entry_price=0.65, size=100.0)
        pnl = calculate_pnl(trade, settlement_value=0.0)
        assert pnl == round(-100.0 * 0.65, 2)  # -65.00

    def test_down_wins(self):
        trade = make_trade(direction="down", entry_price=0.40, size=100.0)
        pnl = calculate_pnl(trade, settlement_value=0.0)
        assert pnl == round(100.0 * (1.0 - 0.40), 2)  # +60.00

    def test_down_loses(self):
        trade = make_trade(direction="down", entry_price=0.40, size=100.0)
        pnl = calculate_pnl(trade, settlement_value=1.0)
        assert pnl == round(-100.0 * 0.40, 2)  # -40.00

    def test_yes_wins(self):
        trade = make_trade(direction="yes", entry_price=0.70, size=50.0)
        pnl = calculate_pnl(trade, settlement_value=1.0)
        assert pnl == round(50.0 * (1.0 - 0.70), 2)  # +15.00

    def test_no_wins(self):
        trade = make_trade(direction="no", entry_price=0.30, size=50.0)
        pnl = calculate_pnl(trade, settlement_value=0.0)
        assert pnl == round(50.0 * (1.0 - 0.30), 2)  # +35.00

    def test_pnl_rounded_to_two_decimal_places(self):
        trade = make_trade(direction="up", entry_price=1/3, size=100.0)
        pnl = calculate_pnl(trade, settlement_value=1.0)
        assert pnl == round(100.0 * (1.0 - 1/3), 2)

    def test_pnl_at_entry_price_50_percent(self):
        """Edge case: 50c entry price."""
        trade = make_trade(direction="up", entry_price=0.50, size=100.0)
        win_pnl = calculate_pnl(trade, settlement_value=1.0)
        loss_pnl = calculate_pnl(trade, settlement_value=0.0)
        assert win_pnl == 50.0
        assert loss_pnl == -50.0


class TestParseMarketResolution:
    """Test market outcome parsing."""

    def test_first_outcome_wins_returns_1(self):
        market = {"closed": True, "outcomePrices": ["0.999", "0.001"], "id": "m1"}
        resolved, value = _parse_market_resolution(market)
        assert resolved is True
        assert value == 1.0

    def test_second_outcome_wins_returns_0(self):
        market = {"closed": True, "outcomePrices": ["0.001", "0.999"], "id": "m1"}
        resolved, value = _parse_market_resolution(market)
        assert resolved is True
        assert value == 0.0

    def test_not_closed_returns_unresolved(self):
        market = {"closed": False, "outcomePrices": ["0.55", "0.45"], "id": "m1"}
        resolved, value = _parse_market_resolution(market)
        assert resolved is False
        assert value is None

    def test_mid_price_not_resolved(self):
        """Market still trading — prices not near 0 or 1."""
        market = {"closed": True, "outcomePrices": ["0.55", "0.45"], "id": "m1"}
        resolved, value = _parse_market_resolution(market)
        assert resolved is False
        assert value is None

    def test_json_string_prices(self):
        """outcomePrices as JSON string (as Polymarket sometimes returns)."""
        market = {"closed": True, "outcomePrices": '["0.999", "0.001"]', "id": "m1"}
        resolved, value = _parse_market_resolution(market)
        assert resolved is True
        assert value == 1.0

    def test_empty_outcome_prices(self):
        market = {"closed": True, "outcomePrices": [], "id": "m1"}
        resolved, value = _parse_market_resolution(market)
        assert resolved is False
        assert value is None


class TestCheckMarketSettlement:
    """Test check_market_settlement integration."""

    @pytest.mark.asyncio
    async def test_settled_trade_returns_pnl(self):
        trade = make_trade(direction="up", entry_price=0.60, size=100.0)

        with patch("backend.core.settlement.fetch_polymarket_resolution", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (True, 1.0)
            is_settled, settlement_value, pnl = await check_market_settlement(trade)

        assert is_settled is True
        assert settlement_value == 1.0
        assert pnl == round(100.0 * (1.0 - 0.60), 2)

    @pytest.mark.asyncio
    async def test_unresolved_market_returns_none(self):
        trade = make_trade(direction="up", entry_price=0.60, size=100.0)

        with patch("backend.core.settlement.fetch_polymarket_resolution", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (False, None)
            is_settled, settlement_value, pnl = await check_market_settlement(trade)

        assert is_settled is False
        assert settlement_value is None
        assert pnl is None
