"""Operational hardening tests: zombie-'closing' recovery + retention pruning."""
from datetime import UTC, datetime, timedelta

import pytest

from backend.data.meteora.paper import run_management_cycle
from backend.data.meteora.service import prune_expired_data
from backend.models.meteora_db import (
    MeteoraCandidate,
    MeteoraDecision,
    MeteoraPoolSnapshot,
    MeteoraPosition,
)


def _mk_closing(db, age_minutes=30):
    pos = MeteoraPosition(
        mode="paper",
        strategy="spot",
        side="two_sided",
        pool_address=f"Zombie{age_minutes}",
        pool_name="Z-SOL",
        status="closing",
        lower_price=90.0,
        upper_price=110.0,
        amount_sol=1.0,
        initial_value_usd=100.0,
        opened_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
    )
    db.add(pos)
    db.commit()
    return pos


@pytest.mark.asyncio
async def test_stale_closing_row_is_recovered(db):
    stale = _mk_closing(db, age_minutes=30)
    fresh = MeteoraPosition(
        mode="paper",
        strategy="spot",
        side="two_sided",
        pool_address="FreshZombie",
        pool_name="F-SOL",
        status="closing",
        lower_price=90.0,
        upper_price=110.0,
        amount_sol=1.0,
        opened_at=datetime.now(UTC),  # too young ⇒ untouched by sweep
    )
    db.add(fresh)
    db.commit()

    await run_management_cycle(session=db)
    db.expire_all()
    swept = db.get(MeteoraPosition, stale.id)
    kept = db.get(MeteoraPosition, fresh.id)
    assert swept.status == "closed"
    assert swept.close_reason == "recovered"
    assert kept.status == "closing"  # young row not force-closed
    # Recovery decision logged
    dec = (
        db.query(MeteoraDecision)
        .filter_by(position_id=stale.id, action="close")
        .one()
    )
    assert dec.reason == "recovered"


@pytest.mark.asyncio
async def test_recovery_sweep_skips_when_no_zombies(db):
    before = (
        db.query(MeteoraPosition).filter_by(status="closing").count(),
    )
    summary = await run_management_cycle(session=db)
    after = db.query(MeteoraPosition).filter_by(status="closing").count()
    assert summary["evaluated"] >= 0
    assert after == before[0]


# ---------------------------------------------------------------------------
# Retention pruning


def _seed_artifacts(db, age_days):
    cutoff = datetime.now(UTC) - timedelta(days=age_days)
    db.add(
        MeteoraPoolSnapshot(
            cycle_id=f"c{age_days}",
            pool_address="P",
            captured_at=cutoff,
            payload={},
        )
    )
    db.add(
        MeteoraCandidate(
            cycle_id=f"c{age_days}",
            pool_address="P",
            degen_score=50.0,
            created_at=cutoff,
        )
    )
    db.add(
        MeteoraDecision(
            actor="test",
            action="skip",
            created_at=cutoff,
        )
    )
    db.commit()


def test_prune_removes_only_expired_rows(db):
    _seed_artifacts(db, age_days=40)   # expired at default 30d
    _seed_artifacts(db, age_days=1)    # kept
    counts = prune_expired_data(db)
    assert counts == {"snapshots": 1, "candidates": 1, "decisions": 1}
    assert db.query(MeteoraPoolSnapshot).count() == 1
    assert db.query(MeteoraCandidate).count() == 1
    assert db.query(MeteoraDecision).count() == 1


def test_prune_respects_custom_window(db):
    _seed_artifacts(db, age_days=3)
    counts = prune_expired_data(db, days=2)
    assert sum(counts.values()) == 3


def test_prune_noop_on_fresh_data(db):
    _seed_artifacts(db, age_days=0)
    counts = prune_expired_data(db, days=7)
    assert sum(counts.values()) == 0
