"""Shared pytest fixtures for PolyEdge backend integration tests."""
# ruff: noqa: E402,F401,F811

import sys
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Stub apscheduler and backend.core.scheduler BEFORE any other imports
# so the startup event doesn't crash on the missing package.
# ---------------------------------------------------------------------------
_sched_stub = MagicMock()
_sched_stub.start_scheduler = MagicMock()
_sched_stub.stop_scheduler = MagicMock()
_sched_stub.log_event = MagicMock()
_sched_stub.is_scheduler_running = MagicMock(return_value=False)
_sched_stub.get_recent_events = MagicMock(return_value=[])
_sched_stub.run_manual_scan = MagicMock(return_value=None)
sys.modules.setdefault("apscheduler", MagicMock())
sys.modules.setdefault("apscheduler.schedulers", MagicMock())
sys.modules.setdefault("apscheduler.schedulers.asyncio", MagicMock())
sys.modules["backend.core.scheduler"] = _sched_stub

# ---------------------------------------------------------------------------
# Build in-memory SQLite engine and redirect the database module to use it
# so every SessionLocal() call (including from startup event / heartbeat)
# hits the same in-memory DB.
# ---------------------------------------------------------------------------
TEST_DB_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch the database module's engine/SessionLocal before app import
from backend.models import database as _db_mod
from backend.models.database import Base

# Import all models so Base.metadata.create_all() creates every table.
# Without these imports, tables like strategy_proposal are missing in test DB.
from backend.models.database import (
    Signal, Trade, BotState, StrategyConfig, DecisionLog, TradeAttempt,
    MarketWatch, WalletConfig, TradeContext, JobQueue, PendingApproval,
    AILog, ActivityLog, MiroFishSignal, StrategyProposal,
    PerformanceMetric, AuditLog, WhaleTransaction, BtcPriceSnapshot,
    ScanLog, CopyTraderEntry, SettlementEvent, EquitySnapshot,
    CalibrationRecord, ResearchItemDB, Alert, AlertConfig,
    Setting, SystemSettings, ErrorLog, Experiment,
)  # noqa: F401
from backend.models.backtest import BacktestRun, BacktestTrade  # noqa: F401
from backend.models.kg_models import LLMCostRecord  # noqa: F401
from backend.core.strategy_performance_registry import StrategyPerformanceSnapshot
from backend.models.database import TransactionEvent

_db_mod.engine = test_engine
_db_mod.SessionLocal = TestSessionLocal

# Create all tables (Base.metadata covers most; ensure_schema covers extras)
Base.metadata.create_all(bind=test_engine)
try:
    _db_mod.ensure_schema()
except Exception:
    pass

# Patch heartbeat module's SessionLocal reference
try:
    from backend.core import heartbeat as _hb
    _hb.SessionLocal = TestSessionLocal
except Exception:
    pass

# ---------------------------------------------------------------------------
# Now import the app (startup event will use the patched SessionLocal)
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.models.database import get_db


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="function")
def client(db):
    def _override_test_db():
        yield db

    app.dependency_overrides[get_db] = _override_test_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="function")
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def cleanup_proposals_between_tests(db):
    from backend.models.database import (
        BotState, Trade, Signal, StrategyProposal, StrategyConfig, ActivityLog, DecisionLog, TradeAttempt, MiroFishSignal
    )
    db.query(Trade).delete()
    db.query(Signal).delete()
    db.query(StrategyProposal).delete()
    db.query(ActivityLog).delete()
    db.query(DecisionLog).delete()
    db.query(TradeAttempt).delete()
    db.query(MiroFishSignal).delete()
    db.query(StrategyConfig).delete()
    
    db.info["allow_live_financial_update"] = True
    for mode in ["paper", "testnet", "live"]:
        state = db.query(BotState).filter_by(mode=mode).first()
        if not state:
            db.add(BotState(
                mode=mode,
                bankroll=10000.0 if mode != "testnet" else 100.0,
                total_trades=0,
                winning_trades=0,
                total_pnl=0.0,
                is_running=True,
            ))
        else:
            state.bankroll = 10000.0 if mode != "testnet" else 100.0
            state.total_trades = 0
            state.winning_trades = 0
            state.total_pnl = 0.0
            state.is_running = True
            state.paper_bankroll = 10000.0
            state.paper_pnl = 0.0
            state.paper_trades = 0
            state.paper_wins = 0
            state.testnet_bankroll = 100.0
            state.testnet_pnl = 0.0
            state.testnet_trades = 0
            state.testnet_wins = 0
    
    db.commit()
    db.info.pop("allow_live_financial_update", None)
    yield
