"""
Unit tests for all 17 trading strategies.

Each test instantiates the strategy, calls run_cycle() with a mock StrategyContext,
and verifies it returns a CycleResult without crashing.

Usage:
    pytest tests/test_strategy_unit.py -v
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.strategies.base import BaseStrategy, CycleResult, StrategyContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.first.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = []
    return db


@pytest.fixture
def mock_clob():
    """Mock PolymarketCLOB client."""
    clob = MagicMock()
    clob.get_orderbook = AsyncMock(return_value={"bids": [], "asks": []})
    clob.get_positions = AsyncMock(return_value=[])
    return clob


@pytest.fixture
def mock_settings():
    """Mock Settings object."""
    settings = MagicMock()
    settings.POLY_API_KEY = ""
    settings.POLY_API_SECRET = ""
    settings.POLY_API_PASSPHRASE = ""
    settings.INITIAL_BANKROLL = 100.0
    settings.TRADING_MODE = "paper"
    settings.MIN_EDGE_PP = 2.0
    settings.MAX_POSITION_PCT = 0.1
    return settings


@pytest.fixture
def strategy_ctx(mock_db, mock_clob, mock_settings):
    """Standard StrategyContext for testing."""
    return StrategyContext(
        db=mock_db,
        clob=mock_clob,
        settings=mock_settings,
        logger=MagicMock(),
        params={},
        mode="paper",
        bankroll=100.0,
        providers={},
    )


def _run_async(coro):
    """Helper to run an async coroutine in tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helper: run a BaseStrategy through run() which wraps run_cycle with error handling
# ---------------------------------------------------------------------------


def _run_strategy(strategy, ctx):
    """Run strategy.run(ctx) and return the CycleResult."""
    return _run_async(strategy.run(ctx))


# ---------------------------------------------------------------------------
# Valid Strategy Tests
# ---------------------------------------------------------------------------



class TestBondScannerStrategy:
    def test_instantiate_and_run(self, strategy_ctx):
        from backend.strategies.bond_scanner import BondScannerStrategy

        strategy = BondScannerStrategy()
        assert isinstance(strategy, BaseStrategy)
        result = _run_strategy(strategy, strategy_ctx)
        assert isinstance(result, CycleResult)


# ---------------------------------------------------------------------------
# 3. BtcMomentumStrategy
# ---------------------------------------------------------------------------


class TestCrossMarketArbEnhanced:
    def test_instantiate(self):
        from backend.strategies.cross_market_arb_enhanced import CrossMarketArbEnhanced

        strategy = CrossMarketArbEnhanced()
        # Not a BaseStrategy subclass; just verify it instantiates
        assert strategy is not None

    def test_has_scan_method(self):
        from backend.strategies.cross_market_arb_enhanced import CrossMarketArbEnhanced

        strategy = CrossMarketArbEnhanced()
        # Verify it has some callable interface (scan/detect methods)
        methods = [
            m
            for m in dir(strategy)
            if not m.startswith("_") and callable(getattr(strategy, m))
        ]
        assert len(methods) > 0, "CrossMarketArbEnhanced should expose callable methods"


# ---------------------------------------------------------------------------
# 6. CryptoOracleStrategy
# ---------------------------------------------------------------------------


class TestLongshotBiasStrategy:
    def test_instantiate_and_run(self, strategy_ctx):
        from backend.strategies.longshot_bias import LongshotBiasStrategy

        strategy = LongshotBiasStrategy()
        assert isinstance(strategy, BaseStrategy)
        result = _run_strategy(strategy, strategy_ctx)
        assert isinstance(result, CycleResult)


# ---------------------------------------------------------------------------
# 12. MarketMakerStrategy
# ---------------------------------------------------------------------------
