"""
Tests for AsyncSQLiteQueue — RQ-012.

Each test gets a fresh on-disk SQLite file (via tmp_path) so rows never leak
between tests and every thread can open its own connection to the same schema.

Note on DB isolation: AsyncSQLiteQueue runs DB ops in a ThreadPoolExecutor.
In-memory SQLite with StaticPool shares one connection across threads causing
"bad parameter" errors; with NullPool each new connection gets an empty DB.
Using a temp file avoids both problems — threads share the same on-disk file.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.models.database import Base, JobQueue
from backend.job_queue.sqlite_queue import AsyncSQLiteQueue


# ---------------------------------------------------------------------------
# Fixture: isolated on-disk temp DB + monkeypatched SessionLocal
# ---------------------------------------------------------------------------

@pytest.fixture()
def queue(monkeypatch, tmp_path):
    """Return a fresh AsyncSQLiteQueue backed by a per-test on-disk SQLite DB."""
    db_file = tmp_path / "test_sq.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Redirect the module-level SessionLocal used inside AsyncSQLiteQueue
    import backend.models.database as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", TestSession)
    import backend.job_queue.sqlite_queue as sq_mod
    monkeypatch.setattr(sq_mod, "SessionLocal", TestSession)

    q = AsyncSQLiteQueue()
    yield q, TestSession
    q.shutdown()
    engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enqueue_creates_job_record(queue):
    q, Session = queue
    job_id = await q.enqueue("market_scan", {"ticker": "BTC"}, priority="high")

    assert job_id is not None

    db = Session()
    try:
        row = db.query(JobQueue).filter(JobQueue.id == int(job_id)).first()
        assert row is not None
        assert row.job_type == "market_scan"
        assert row.payload == {"ticker": "BTC"}
        assert row.priority == "high"
        assert row.status == "pending"
        assert row.scheduled_at is not None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_dequeue_priority_order(queue):
    q, _ = queue
    await q.enqueue("market_scan", {"order": 1}, priority="low")
    await q.enqueue("market_scan", {"order": 2}, priority="medium")
    await q.enqueue("market_scan", {"order": 3}, priority="high")
    await q.enqueue("market_scan", {"order": 4}, priority="critical")

    job1 = await q.dequeue()
    job2 = await q.dequeue()
    job3 = await q.dequeue()
    job4 = await q.dequeue()

    assert job1.priority == "critical"
    assert job2.priority == "high"
    assert job3.priority == "medium"
    assert job4.priority == "low"


@pytest.mark.asyncio
async def test_idempotency_constraint(queue):
    q, Session = queue
    id1 = await q.enqueue(
        "market_scan", {"ticker": "BTC"}, idempotency_key="scan-001"
    )
    id2 = await q.enqueue(
        "market_scan", {"ticker": "BTC"}, idempotency_key="scan-001"
    )

    assert id1 == id2

    db = Session()
    try:
        count = db.query(JobQueue).filter(
            JobQueue.idempotency_key == "scan-001"
        ).count()
        assert count == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_complete_updates_status(queue):
    q, Session = queue
    job_id = await q.enqueue("market_scan", {})
    job = await q.dequeue()
    assert job is not None
    await q.complete(job.job_id)

    db = Session()
    try:
        row = db.query(JobQueue).filter(JobQueue.id == int(job_id)).first()
        assert row.status == "completed"
        assert row.completed_at is not None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_fail_updates_status_and_retry_count(queue):
    q, Session = queue
    job_id = await q.enqueue("market_scan", {})
    job = await q.dequeue()
    assert job is not None
    await q.fail(job.job_id, "something went wrong")

    db = Session()
    try:
        row = db.query(JobQueue).filter(JobQueue.id == int(job_id)).first()
        # retry_count should be 1, still pending because < max_retries (3)
        assert row.retry_count == 1
        assert row.error_message == "something went wrong"
        assert row.status == "pending"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_fail_max_retries_marks_failed(queue):
    q, Session = queue
    job_id = await q.enqueue("market_scan", {})

    # Dequeue -> fail until retry_count == max_retries (3 by default)
    for _ in range(3):
        job = await q.dequeue()
        assert job is not None, "Job should be dequeueable for retry"
        await q.fail(job.job_id, "repeated failure")

    db = Session()
    try:
        row = db.query(JobQueue).filter(JobQueue.id == int(job_id)).first()
        assert row.status == "failed"
        assert row.retry_count == 3
    finally:
        db.close()


@pytest.mark.asyncio
async def test_get_pending_count(queue):
    q, _ = queue
    for i in range(5):
        await q.enqueue("market_scan", {"i": i})

    # Dequeue 2 (marks them processing, not pending)
    await q.dequeue()
    await q.dequeue()

    count = await q.get_pending_count()
    assert count == 3
