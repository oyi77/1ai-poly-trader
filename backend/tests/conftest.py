"""Shared pytest fixtures for PolyEdge backend integration tests."""
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

# Seed initial BotState so /api/stats doesn't 404
from backend.models.database import BotState
from backend.config import settings as _settings

_seed_db = TestSessionLocal()
try:
    for mode in ["paper", "testnet", "live"]:
        if not _seed_db.query(BotState).filter_by(mode=mode).first():
            initial_bankroll = _settings.INITIAL_BANKROLL if mode != "testnet" else 100.0
            _seed_db.add(BotState(
                id=1,
                mode=mode,
                bankroll=initial_bankroll,
                total_trades=0,
                winning_trades=0,
                total_pnl=0.0,
                is_running=True,
            ))
    _seed_db.commit()
finally:
    _seed_db.close()

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


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient backed by in-memory SQLite."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="session")
def db():
    """Raw DB session for seeding test data."""
    session = TestSessionLocal()
    yield session
    session.close()
