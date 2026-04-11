"""Tests for backend.core.strategy_executor — strategy decision → trade pipeline."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Stub heavy scheduler deps before any app imports
# ---------------------------------------------------------------------------
_sched_stub = MagicMock()
_sched_stub.start_scheduler = MagicMock()
_sched_stub.stop_scheduler = MagicMock()
_sched_stub.log_event = MagicMock()
_sched_stub.is_scheduler_running = MagicMock(return_value=False)
sys.modules.setdefault("apscheduler", MagicMock())
sys.modules.setdefault("apscheduler.schedulers", MagicMock())
sys.modules.setdefault("apscheduler.schedulers.asyncio", MagicMock())
sys.modules["backend.core.scheduler"] = _sched_stub

# ---------------------------------------------------------------------------
# In-memory DB wiring (mirrors conftest pattern)
# ---------------------------------------------------------------------------
from backend.models import database as _db_mod
from backend.models.database import Base, BotState

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

_db_mod.engine = _test_engine
_db_mod.SessionLocal = _TestSession

Base.metadata.create_all(bind=_test_engine)
try:
    _db_mod.ensure_schema()
except Exception:
    pass

try:
    from backend.core import heartbeat as _hb

    _hb.SessionLocal = _TestSession
except Exception:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_state(db, bankroll=1000.0, paper_bankroll=1000.0, is_running=True):
    """Insert or reset BotState for a test."""
    state = db.query(BotState).first()
    if state:
        state.bankroll = bankroll
        state.paper_bankroll = paper_bankroll
        state.is_running = is_running
        state.total_trades = 0
        state.paper_trades = 0
    else:
        state = BotState(
            bankroll=bankroll,
            paper_bankroll=paper_bankroll,
            is_running=is_running,
            total_trades=0,
            paper_trades=0,
        )
        db.add(state)
    db.commit()
    return state


def _make_decision(**overrides) -> dict:
    base = {
        "market_ticker": "test-market-001",
        "direction": "yes",
        "size": 50.0,
        "entry_price": 0.55,
        "edge": 0.08,
        "confidence": 0.75,
        "model_probability": 0.63,
        "platform": "polymarket",
        "reasoning": "test signal",
        "token_id": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPaperTradeCreatesRecord:
    @pytest.mark.asyncio
    async def test_paper_trade_creates_record(self):
        """In paper mode, execute_decision creates a Trade row in the DB."""
        from backend.models.database import Trade, Signal

        db = _TestSession()
        _seed_state(db)
        db.close()

        with (
            patch("backend.core.strategy_executor.settings") as mock_settings,
            patch("backend.core.strategy_executor.SessionLocal", _TestSession),
            patch("backend.core.strategy_executor._broadcast_event"),
        ):
            mock_settings.TRADING_MODE = "paper"

            from backend.core.strategy_executor import execute_decision

            result = await execute_decision(_make_decision(), "test_strategy")

        assert result is not None
        assert result["market_ticker"] == "test-market-001"
        assert result["fill_price"] == pytest.approx(0.55)

        check_db = _TestSession()
        try:
            trade = (
                check_db.query(Trade)
                .filter(Trade.market_ticker == "test-market-001")
                .first()
            )
            assert trade is not None
            assert trade.strategy == "test_strategy"
            assert trade.direction == "yes"
            assert trade.trading_mode == "paper"

            sig = (
                check_db.query(Signal)
                .filter(Signal.market_ticker == "test-market-001")
                .first()
            )
            assert sig is not None
            assert sig.executed is True
        finally:
            check_db.close()


class TestRiskRejection:
    @pytest.mark.asyncio
    async def test_risk_rejection_returns_none(self):
        """RiskManager rejection causes execute_decision to return None."""
        from backend.core.risk_manager import RiskDecision, RiskManager

        # Create fresh test engine for this test to ensure isolation
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestSession = sessionmaker(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        # Seed state into the TEST engine (not the module-level one)
        db = TestSession()
        _seed_state(db)
        db.close()

        # Create mock RiskManager with rejection
        mock_rm = MagicMock(spec=RiskManager)
        mock_rm.validate_trade.return_value = RiskDecision(
            allowed=False, reason="daily loss limit hit", adjusted_size=0.0
        )

        with (
            patch("backend.core.strategy_executor.settings") as mock_settings,
            patch("backend.core.strategy_executor.SessionLocal", TestSession),
            patch("backend.core.strategy_executor._broadcast_event"),
        ):
            mock_settings.TRADING_MODE = "paper"

            from backend.core.strategy_executor import execute_decision
            from backend.core import strategy_executor as se_module

            # Replace the module-level risk_manager instance
            original_rm = se_module.risk_manager
            se_module.risk_manager = mock_rm
            try:
                result = await execute_decision(
                    _make_decision(market_ticker="reject-market"), "test_strategy"
                )
                assert result is None
                mock_rm.validate_trade.assert_called_once()
            finally:
                se_module.risk_manager = original_rm


class TestUpdatesBankroll:
    @pytest.mark.asyncio
    async def test_updates_paper_bankroll(self):
        """Paper trade does NOT deduct bankroll at entry — settlement handles all PNL."""
        # Create fresh test engine for this test to ensure isolation
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestSession = sessionmaker(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestSession()
        _seed_state(db, paper_bankroll=500.0)
        db.close()

        with (
            patch("backend.core.strategy_executor.settings") as mock_settings,
            patch("backend.core.strategy_executor.SessionLocal", TestSession),
            patch("backend.core.strategy_executor._broadcast_event"),
        ):
            mock_settings.TRADING_MODE = "paper"

            from backend.core.strategy_executor import execute_decision

            result = await execute_decision(
                _make_decision(market_ticker="bankroll-market", size=50.0),
                "test_strategy",
            )

        assert result is not None

        check_db = TestSession()
        try:
            state = check_db.query(BotState).first()
            # Bankroll should remain unchanged at entry — settlement handles PNL
            assert state.paper_bankroll == 500.0
        finally:
            check_db.close()


class TestCreatesSignalRecord:
    @pytest.mark.asyncio
    async def test_creates_signal_record(self):
        """execute_decision creates a Signal row for calibration tracking."""
        from backend.models.database import Signal

        # Create fresh test engine for this test to ensure isolation
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestSession = sessionmaker(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestSession()
        _seed_state(db)
        db.close()

        ticker = "signal-track-market"

        with (
            patch("backend.core.strategy_executor.settings") as mock_settings,
            patch("backend.core.strategy_executor.SessionLocal", TestSession),
            patch("backend.core.strategy_executor._broadcast_event"),
        ):
            mock_settings.TRADING_MODE = "paper"

            from backend.core.strategy_executor import execute_decision

            result = await execute_decision(
                _make_decision(market_ticker=ticker, reasoning="signal reason"),
                "calibration_strategy",
            )

        assert result is not None

        check_db = TestSession()
        try:
            sig = (
                check_db.query(Signal)
                .filter(Signal.market_ticker == ticker)
                .order_by(Signal.id.desc())
                .first()
            )
            assert sig is not None
            assert sig.track_name == "calibration_strategy"
            assert sig.executed is True
            assert sig.execution_mode == "paper"
        finally:
            check_db.close()


class TestMaxTradesPerCycle:
    @pytest.mark.asyncio
    async def test_max_trades_per_cycle(self):
        """execute_decisions caps at MAX_TRADES_PER_CYCLE (2)."""
        # Create fresh test engine for this test to ensure isolation
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestSession = sessionmaker(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestSession()
        _seed_state(db, paper_bankroll=10000.0)
        db.close()

        # Build 5 distinct decisions
        decisions = [
            _make_decision(market_ticker=f"cap-market-{i}", size=10.0) for i in range(5)
        ]

        with (
            patch("backend.core.strategy_executor.settings") as mock_settings,
            patch("backend.core.strategy_executor.SessionLocal", TestSession),
            patch("backend.core.strategy_executor._broadcast_event"),
        ):
            mock_settings.TRADING_MODE = "paper"

            from backend.core.strategy_executor import execute_decisions

            results = await execute_decisions(decisions, "cap_strategy")

        assert len(results) <= 2


class TestLiveModeCallsCLOB:
    @pytest.mark.asyncio
    async def test_live_mode_calls_clob(self):
        """In live mode, place_limit_order is called and its result drives trade creation."""
        from backend.data.polymarket_clob import OrderResult

        # Create fresh test engine for this test to ensure isolation
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestSession = sessionmaker(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestSession()
        _seed_state(db, bankroll=2000.0, paper_bankroll=2000.0)
        db.close()

        mock_order_result = OrderResult(
            success=True,
            order_id="live-order-xyz",
            fill_price=0.56,
            fill_size=50.0,
        )

        mock_clob = AsyncMock()
        mock_clob.place_limit_order = AsyncMock(return_value=mock_order_result)
        mock_clob.__aenter__ = AsyncMock(return_value=mock_clob)
        mock_clob.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("backend.core.strategy_executor.settings") as mock_settings,
            patch("backend.core.strategy_executor.SessionLocal", TestSession),
            patch("backend.core.strategy_executor._broadcast_event"),
            patch(
                "backend.data.polymarket_clob.clob_from_settings",
                return_value=mock_clob,
            ),
        ):
            mock_settings.TRADING_MODE = "live"

            from backend.core.strategy_executor import execute_decision

            result = await execute_decision(
                _make_decision(
                    market_ticker="live-market-001",
                    token_id="token-abc-123",
                    size=50.0,
                ),
                "live_strategy",
            )

        assert result is not None
        mock_clob.place_limit_order.assert_awaited_once()
        assert result["clob_order_id"] == "live-order-xyz"
