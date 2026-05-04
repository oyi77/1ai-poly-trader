"""Tests for enhanced risk manager — drawdown breaker, per-market limits, exposure."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.risk_manager import RiskManager
from backend.models.database import Base, Trade


@dataclass
class MockSettings:
    INITIAL_BANKROLL: float = 1000.0
    DAILY_LOSS_LIMIT: float = 300.0
    MAX_POSITION_FRACTION: float = 0.05
    MAX_TOTAL_EXPOSURE_FRACTION: float = 0.50
    SLIPPAGE_TOLERANCE: float = 0.02
    DAILY_DRAWDOWN_LIMIT_PCT: float = 0.10
    WEEKLY_DRAWDOWN_LIMIT_PCT: float = 0.20
    TRADING_MODE: str = "paper"
    AUTO_APPROVE_MIN_CONFIDENCE: float = 0.50
    MIN_ORDER_USDC: float = 5.0
    PAPER_MIN_ORDER_USDC: float = 1.0
    DRAWDOWN_BREAKER_ENABLED_PER_MODE: dict = None
    DAILY_LOSS_LIMIT_ENABLED_PER_MODE: dict = None

    def __post_init__(self):
        if self.DRAWDOWN_BREAKER_ENABLED_PER_MODE is None:
            self.DRAWDOWN_BREAKER_ENABLED_PER_MODE = {
                "paper": True,
                "testnet": True,
                "live": True,
            }
        if self.DAILY_LOSS_LIMIT_ENABLED_PER_MODE is None:
            self.DAILY_LOSS_LIMIT_ENABLED_PER_MODE = {
                "paper": True,
                "testnet": True,
                "live": True,
            }


def make_rm():
    return RiskManager(settings_obj=MockSettings())


@pytest.fixture()
def risk_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


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
            size=5.0,
            current_exposure=0.0,
            bankroll=1000.0,
            confidence=0.01,
            mode="paper",
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
            0.0,  # _daily_loss_exceeded: today's pnl ok
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
            1,  # unsettled trade count
        ]

        rm = make_rm()
        result = rm.validate_trade(
            size=5.0,
            current_exposure=0.0,
            bankroll=1000.0,
            confidence=0.7,
            market_ticker="btc-5min-123",
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
    def test_live_exposure_uses_portfolio_value_not_cash_plus_exposure(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0

        rm = make_rm()
        result = rm.validate_trade(
            size=20.0,
            current_exposure=45.0,
            bankroll=100.0,
            confidence=0.7,
            mode="live",
        )

        assert result.allowed is True
        assert result.adjusted_size == 2.75

    @patch("backend.core.risk_manager.SessionLocal")
    def test_slippage_rejection(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0

        rm = make_rm()
        result = rm.validate_trade(
            size=5.0,
            current_exposure=0.0,
            bankroll=1000.0,
            confidence=0.7,
            slippage=0.05,
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
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [
            -150.0,
            -150.0,
        ]

        rm = make_rm()
        status = rm.check_drawdown(bankroll=1000.0)
        assert status.is_breached is True
        assert "24h" in status.breach_reason

    @patch("backend.core.risk_manager.SessionLocal")
    def test_weekly_drawdown_breached(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [
            -50.0,
            -250.0,
        ]

        rm = make_rm()
        status = rm.check_drawdown(bankroll=1000.0)
        assert status.is_breached is True
        assert "7d" in status.breach_reason

    def test_drawdown_includes_null_settlement_source_but_excludes_backfill(self, risk_db):
        now = datetime.now(timezone.utc)
        normal_loss = Trade(
            market_ticker="normal-loss",
            direction="up",
            entry_price=0.5,
            size=40.0,
            settled=True,
            result="loss",
            pnl=-40.0,
            trading_mode="paper",
            settlement_time=now,
            settlement_source=None,
        )
        historical_backfill = Trade(
            market_ticker="historical-backfill",
            direction="up",
            entry_price=0.5,
            size=500.0,
            settled=True,
            result="loss",
            pnl=-500.0,
            trading_mode="paper",
            settlement_time=now,
            settlement_source="backfill_conservative_loss",
        )
        risk_db.add_all([normal_loss, historical_backfill])
        risk_db.commit()

        rm = make_rm()
        status = rm.check_drawdown(bankroll=1000.0, db=risk_db, mode="paper")

        assert status.daily_pnl == pytest.approx(-40.0)
        assert status.weekly_pnl == pytest.approx(-40.0)
        assert status.is_breached is False


class TestBreakerEnabledPerMode:
    """Test that drawdown and daily-loss breakers can be disabled per trading mode."""

    def _make_rm_with_breakers(self, drawdown_enabled, daily_loss_enabled, mode="paper"):
        s = MockSettings()
        s.DRAWDOWN_BREAKER_ENABLED_PER_MODE = {
            "paper": drawdown_enabled,
            "testnet": True,
            "live": True,
        }
        s.DAILY_LOSS_LIMIT_ENABLED_PER_MODE = {
            "paper": daily_loss_enabled,
            "testnet": True,
            "live": True,
        }
        s.TRADING_MODE = mode
        return RiskManager(settings_obj=s)

    @patch("backend.core.risk_manager.SessionLocal")
    def test_paper_mode_skips_drawdown_breaker_when_disabled(self, mock_session_cls):
        rm = self._make_rm_with_breakers(drawdown_enabled=False, daily_loss_enabled=False)
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0, confidence=0.7, mode="paper",
        )
        assert result.allowed is True

    @patch("backend.core.risk_manager.SessionLocal")
    def test_paper_mode_skips_daily_loss_when_disabled(self, mock_session_cls):
        rm = self._make_rm_with_breakers(drawdown_enabled=False, daily_loss_enabled=False)
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0, confidence=0.7, mode="paper",
        )
        assert result.allowed is True

    @patch("backend.core.risk_manager.SessionLocal")
    def test_paper_mode_skips_both_breakers(self, mock_session_cls):
        rm = self._make_rm_with_breakers(drawdown_enabled=False, daily_loss_enabled=False)
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0, confidence=0.7, mode="paper",
        )
        assert result.allowed is True

    @patch("backend.core.risk_manager.SessionLocal")
    def test_live_mode_still_enforces_drawdown(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0
        rm = self._make_rm_with_breakers(drawdown_enabled=True, daily_loss_enabled=True, mode="live")
        result = rm.validate_trade(
            size=5.0, current_exposure=0.0, bankroll=1000.0, confidence=0.7, mode="live",
        )
        assert result.allowed is True

    def test_breaker_enabled_per_mode_defaults_to_true(self):
        rm = make_rm()
        assert rm._breaker_enabled_for_mode("drawdown", "live") is True
        assert rm._breaker_enabled_for_mode("drawdown", "testnet") is True
        assert rm._breaker_enabled_for_mode("daily_loss", "live") is True
        assert rm._breaker_enabled_for_mode("daily_loss", "testnet") is True

    def test_breaker_disabled_for_paper_with_config(self):
        s = MockSettings()
        s.DRAWDOWN_BREAKER_ENABLED_PER_MODE = {
            "paper": False, "testnet": True, "live": True,
        }
        rm = RiskManager(settings_obj=s)
        assert rm._breaker_enabled_for_mode("drawdown", "paper") is False
        assert rm._breaker_enabled_for_mode("drawdown", "live") is True
        assert rm._breaker_enabled_for_mode("drawdown", "testnet") is True
        assert rm._breaker_enabled_for_mode("daily_loss", "live") is True
        assert rm._breaker_enabled_for_mode("daily_loss", "testnet") is True

    def test_breaker_disabled_for_paper_with_config(self):
        s = MockSettings()
        s.DRAWDOWN_BREAKER_ENABLED_PER_MODE = {
            "paper": False, "testnet": True, "live": True,
        }
        rm = RiskManager(settings_obj=s)
        assert rm._breaker_enabled_for_mode("drawdown", "paper") is False
        assert rm._breaker_enabled_for_mode("drawdown", "live") is True
