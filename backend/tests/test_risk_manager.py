"""Tests for enhanced risk manager — drawdown breaker, per-market limits, exposure."""
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

from backend.core.risk_manager import RiskManager, RiskDecision, DrawdownStatus


@dataclass
class MockSettings:
    DAILY_LOSS_LIMIT: float = 300.0
    MAX_POSITION_FRACTION: float = 0.05
    MAX_TOTAL_EXPOSURE_FRACTION: float = 0.50
    SLIPPAGE_TOLERANCE: float = 0.02
    DAILY_DRAWDOWN_LIMIT_PCT: float = 0.10
    WEEKLY_DRAWDOWN_LIMIT_PCT: float = 0.20


def make_rm():
    return RiskManager(settings_obj=MockSettings())


class TestValidateTrade:
    @patch("backend.core.risk_manager.SessionLocal")
    def test_normal_trade_allowed(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0

        rm = make_rm()
        result = rm.validate_trade(
            size=5.0, current_exposure=10.0, bankroll=1000.0, confidence=0.7
        )
        assert result.allowed is True
        assert result.reason == "ok"
        assert result.adjusted_size == 5.0

    def test_low_confidence_rejected(self):
        rm = make_rm()
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0, confidence=0.3
        )
        assert result.allowed is False
        assert "confidence" in result.reason

    @patch("backend.core.risk_manager.SessionLocal")
    def test_daily_loss_limit_blocks(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = -350.0

        rm = make_rm()
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0, confidence=0.7
        )
        assert result.allowed is False
        assert "daily loss limit" in result.reason

    @patch("backend.core.risk_manager.SessionLocal")
    def test_drawdown_breaker_blocks(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [
            0.0,     # _daily_loss_exceeded: today's pnl ok
            -120.0,  # check_drawdown: 24h pnl (12% > 10% limit)
            -120.0,  # check_drawdown: 7d pnl
        ]

        rm = make_rm()
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0, confidence=0.7
        )
        assert result.allowed is False
        assert "drawdown" in result.reason

    @patch("backend.core.risk_manager.SessionLocal")
    def test_duplicate_market_blocked(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [
            0.0,  # daily loss check
            0.0,  # drawdown daily
            0.0,  # drawdown weekly
            1,    # unsettled trade count
        ]

        rm = make_rm()
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0,
            confidence=0.7, market_ticker="btc-5min-123"
        )
        assert result.allowed is False
        assert "unsettled trade" in result.reason

    @patch("backend.core.risk_manager.SessionLocal")
    def test_exposure_limit_reduces_size(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0

        rm = make_rm()
        result = rm.validate_trade(
            size=20.0, current_exposure=45.0, bankroll=100.0, confidence=0.7
        )
        assert result.allowed is True
        assert result.adjusted_size == 5.0

    @patch("backend.core.risk_manager.SessionLocal")
    def test_slippage_rejection(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0

        rm = make_rm()
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0,
            confidence=0.7, slippage=0.05
        )
        assert result.allowed is False
        assert "slippage" in result.reason

    @patch("backend.core.risk_manager.SessionLocal")
    def test_position_size_clamped(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0

        rm = make_rm()
        # bankroll=10000, MAX_POSITION_FRACTION=0.05 -> max 500
        result = rm.validate_trade(
            size=1000.0, current_exposure=0.0, bankroll=10000.0, confidence=0.9
        )
        assert result.allowed is True
        assert result.adjusted_size <= 10000 * 0.05 + 1e-6


class TestCheckDrawdown:
    @patch("backend.core.risk_manager.SessionLocal")
    def test_no_drawdown(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [5.0, 10.0]

        rm = make_rm()
        status = rm.check_drawdown(bankroll=1000.0)
        assert status.is_breached is False
        assert status.daily_pnl == 5.0
        assert status.weekly_pnl == 10.0

    @patch("backend.core.risk_manager.SessionLocal")
    def test_daily_drawdown_breached(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [-150.0, -150.0]

        rm = make_rm()
        status = rm.check_drawdown(bankroll=1000.0)
        assert status.is_breached is True
        assert "24h" in status.breach_reason

    @patch("backend.core.risk_manager.SessionLocal")
    def test_weekly_drawdown_breached(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [-50.0, -250.0]

        rm = make_rm()
        status = rm.check_drawdown(bankroll=1000.0)
        assert status.is_breached is True
        assert "7d" in status.breach_reason
