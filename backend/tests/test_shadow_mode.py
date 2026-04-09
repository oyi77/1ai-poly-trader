"""Tests for ShadowRunner in backend.core.shadow_mode."""

import pytest
from backend.core.shadow_mode import ShadowRunner, ShadowTrade, ShadowPerformance


def test_record_and_settle_win():
    """Record a trade and settle it as a win — P&L should be positive."""
    runner = ShadowRunner()
    trade = runner.record_signal(
        market_ticker="BTC-UP-12345",
        direction="up",
        entry_price=0.55,
        size=100.0,
        model_prob=0.70,
        strategy="btc_5min",
    )
    assert isinstance(trade, ShadowTrade)
    assert trade.settled is False

    # settlement_value=1.0 means UP won
    runner.settle("BTC-UP-12345", settlement_value=1.0)

    assert trade.settled is True
    assert trade.pnl is not None
    assert trade.pnl > 0  # (1.0 - 0.55) * 100 = 45.0
    assert abs(trade.pnl - 45.0) < 1e-6


def test_settle_loss():
    """Record a trade and settle it as a loss — P&L should be negative."""
    runner = ShadowRunner()
    trade = runner.record_signal(
        market_ticker="BTC-UP-99999",
        direction="up",
        entry_price=0.60,
        size=50.0,
        model_prob=0.65,
        strategy="btc_5min",
    )
    # settlement_value=0.0 means DOWN won (up loses)
    runner.settle("BTC-UP-99999", settlement_value=0.0)

    assert trade.settled is True
    assert trade.pnl is not None
    assert trade.pnl < 0  # -0.60 * 50 = -30.0
    assert abs(trade.pnl - (-30.0)) < 1e-6


def test_performance_metrics():
    """Multiple trades verify win_rate and total_pnl are computed correctly."""
    runner = ShadowRunner()

    # Trade 1: win — direction=up, settlement=1.0
    runner.record_signal("MKT-A", "up", 0.50, 100.0, 0.70, "strat_a")
    runner.settle("MKT-A", 1.0)  # pnl = (1-0.5)*100 = 50

    # Trade 2: loss — direction=down, settlement=1.0 (up won, down loses)
    runner.record_signal("MKT-B", "down", 0.40, 80.0, 0.65, "strat_a")
    runner.settle("MKT-B", 1.0)  # pnl = -0.40*80 = -32

    # Trade 3: win — direction=down, settlement=0.0 (down won)
    runner.record_signal("MKT-C", "down", 0.45, 60.0, 0.60, "strat_b")
    runner.settle("MKT-C", 0.0)  # pnl = (1-0.45)*60 = 33

    perf = runner.get_performance()

    assert perf.total_trades == 3
    assert perf.settled_trades == 3
    assert abs(perf.total_pnl - (50.0 - 32.0 + 33.0)) < 1e-6  # 51.0
    assert abs(perf.win_rate - (2 / 3)) < 1e-6
    assert "strat_a" in perf.strategy_breakdown
    assert "strat_b" in perf.strategy_breakdown
    assert abs(perf.strategy_breakdown["strat_a"] - (50.0 - 32.0)) < 1e-6
    assert abs(perf.strategy_breakdown["strat_b"] - 33.0) < 1e-6


def test_compare_with_live():
    """compare_with_live returns correct shadow vs live comparison."""
    runner = ShadowRunner()

    runner.record_signal("MKT-X", "up", 0.50, 100.0, 0.75, "strat_x")
    runner.settle("MKT-X", 1.0)  # pnl = 50.0

    result = runner.compare_with_live(live_pnl=30.0)

    assert result["shadow_pnl"] == 50.0
    assert result["live_pnl"] == 30.0
    assert abs(result["difference"] - 20.0) < 1e-6
    assert result["shadow_better"] is True

    # Case where shadow is worse
    result2 = runner.compare_with_live(live_pnl=80.0)
    assert result2["shadow_better"] is False
    assert abs(result2["difference"] - (50.0 - 80.0)) < 1e-6
