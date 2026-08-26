"""Live executor tests — gating, kill switches, dry-run pipeline.

No network, no keypair material: the flag/wallet env is monkeypatched per
test; DryRunTxBuilder stands in for on-chain construction.
"""
import pytest

from backend.data.meteora.executor import (
    DryRunTxBuilder,
    ExecutorError,
    RiskLimits,
    check_risk_gates,
    close_live_position,
    deploy_live_position,
    live_enabled,
    load_keypair,
)
from backend.models.meteora_db import MeteoraDecision, MeteoraPosition

ORDER = {
    "pool_address": "PoolExec",
    "pool_name": "EXEC-SOL",
    "strategy": "spot",
    "side": "two_sided",
    "lower_price": 95.0,
    "upper_price": 105.0,
    "amount_sol": 0.5,
    "bin_step": 100,
    "signal_snapshot": {"organic_score": 80},
}


# ---------------------------------------------------------------------------
# Gates


def test_live_disabled_by_default(monkeypatch):
    monkeypatch.delenv("METEORA_LIVE_ENABLED", raising=False)
    assert live_enabled() is False


async def test_deploy_refuses_without_flag(monkeypatch):
    monkeypatch.delenv("METEORA_LIVE_ENABLED", raising=False)
    with pytest.raises(ExecutorError, match="METEORA_LIVE_ENABLED"):
        await deploy_live_position(dict(ORDER))


def test_load_keypair_requires_secret(monkeypatch):
    monkeypatch.delenv("METEORA_WALLET_PRIVATE_KEY", raising=False)
    with pytest.raises(ExecutorError, match="not set"):
        load_keypair()


def test_rpc_url_required(monkeypatch):
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "METEORA_RPC_URL", "", raising=False)
    from backend.data.meteora.executor import rpc_url

    with pytest.raises(ExecutorError, match="METEORA_RPC_URL"):
        rpc_url()


# ---------------------------------------------------------------------------
# Risk gates


def _closed(db, idx, pnl_usd, days_ago=0):
    from datetime import UTC, datetime, timedelta

    db.add(
        MeteoraPosition(
            mode="live",
            strategy="spot",
            side="two_sided",
            pool_address=f"EP{idx}",
            status="closed",
            lower_price=90.0,
            upper_price=110.0,
            amount_sol=1.0,
            initial_value_usd=100.0,
            final_value_usd=100.0 + pnl_usd,
            fees_earned_usd=0.0,
            opened_at=datetime.now(UTC) - timedelta(days=days_ago + 1),
            closed_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )


def test_gate_blocks_when_max_positions_open(db):
    for i in range(RiskLimits.max_open_positions):
        db.add(
            MeteoraPosition(
                mode="live",
                strategy="spot",
                side="two_sided",
                pool_address=f"OP{i}",
                status="open",
                lower_price=90.0,
                upper_price=110.0,
                amount_sol=0.1,
            )
        )
    db.commit()
    with pytest.raises(ExecutorError, match="max_open_positions"):
        check_risk_gates(db, RiskLimits())


def test_daily_loss_cap_halts_deploys(db):
    _closed(db, 1, -30.0, days_ago=0)
    db.commit()
    with pytest.raises(ExecutorError, match="daily loss cap"):
        check_risk_gates(db, RiskLimits())


def test_drawdown_halt_trips_on_aggregate(db):
    for i in range(5):
        _closed(db, i, -30.0, days_ago=i + 1)
    db.commit()
    with pytest.raises(ExecutorError, match="drawdown halt"):
        check_risk_gates(db, RiskLimits())


def test_gates_pass_when_healthy(db):
    _closed(db, 1, 3.0, days_ago=0)
    db.commit()
    check_risk_gates(db, RiskLimits())  # no exception


# ---------------------------------------------------------------------------
# Dry-run pipeline


@pytest.mark.asyncio
async def test_dry_run_deploy_creates_live_row_and_decision(db, monkeypatch):
    monkeypatch.setenv("METEORA_LIVE_ENABLED", "1")

    async def price_ok(pool_address):
        return 100.0  # matches entry mid ⇒ drift gate passes

    result = await deploy_live_position(dict(ORDER), price_fetch=price_ok)
    assert result["signature"].startswith("dryrun-open-")
    row = db.get(MeteoraPosition, result["position_id"])
    db.expire_all()
    row = db.get(MeteoraPosition, result["position_id"])
    assert row.mode == "live" and row.status == "open"
    dec = (
        db.query(MeteoraDecision)
        .filter_by(position_id=row.id, action="deploy", mode="live")
        .one()
    )
    assert "DryRunTxBuilder" in dec.summary


async def test_dry_run_builder_validation():
    b = DryRunTxBuilder()
    with pytest.raises(ExecutorError, match="missing fields"):
        await b.open_position({"pool_address": "x"})
    with pytest.raises(ExecutorError, match="positive"):
        await b.open_position(dict(ORDER, amount_sol=-1))
    with pytest.raises(ExecutorError, match="lower_price"):
        await b.open_position(dict(ORDER, lower_price=110, upper_price=100))
    sig = await b.close_position({"position_mint": "mint123456"})
    assert sig.startswith("dryrun-close-")


@pytest.mark.asyncio
async def test_price_drift_gate_rejects(db, monkeypatch):
    monkeypatch.setenv("METEORA_LIVE_ENABLED", "1")

    async def price_far(pool_address):
        return 110.0  # mid=100 ⇒ 10% drift

    with pytest.raises(ExecutorError, match="price drift gate"):
        await deploy_live_position(dict(ORDER), price_fetch=price_far)


@pytest.mark.asyncio
async def test_duplicate_open_guard_rejects(db, monkeypatch):
    monkeypatch.setenv("METEORA_LIVE_ENABLED", "1")
    db.add(
        MeteoraPosition(
            mode="live",
            strategy=ORDER["strategy"],
            side="two_sided",
            pool_address=ORDER["pool_address"],
            status="open",
            lower_price=95.0,
            upper_price=105.0,
            amount_sol=0.1,
        )
    )
    db.commit()

    async def price_ok(pool_address):
        return 100.0

    with pytest.raises(ExecutorError, match="duplicate open live position"):
        await deploy_live_position(dict(ORDER), price_fetch=price_ok)


@pytest.mark.asyncio
async def test_close_live_position_full_flow(db, monkeypatch):
    monkeypatch.setenv("METEORA_LIVE_ENABLED", "1")
    opened = await deploy_live_position(dict(ORDER), price_fetch=price_hundred)
    pid = opened["position_id"]

    result = await close_live_position(pid, exit_price=101.0)
    assert result["signature"].startswith("dryrun-close-")
    db.expire_all()
    row = db.get(MeteoraPosition, pid)
    assert row.status == "closed"
    assert row.tx_signature_close.startswith("dryrun-close-")


async def price_hundred(pool_address):
    return 100.0
