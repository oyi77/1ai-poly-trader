"""Paper-agent exit doctrine + darwin learning loop tests.

Pure exit-engine cases use synthetic PositionViews; integration cases run the
real management cycle against the conftest in-memory DB with an injected
async price feed (no network).
"""
from datetime import UTC, datetime, timedelta

import pytest

from backend.data.meteora.learning import (
    CEILING,
    FLOOR,
    derive_lesson,
    recalc_signal_weights,
    should_recalc,
)
from backend.data.meteora.paper import (
    ExitRules,
    PositionView,
    close_paper_position,
    evaluate_exit,
    open_paper_position,
)
from backend.models.meteora_db import (
    MeteoraCandidate,
    MeteoraCooldown,
    MeteoraDecision,
    MeteoraPosition,
    MeteoraSignalWeight,
)

RULES = ExitRules()


def view(**kw):
    base = dict(
        pnl_pct=0.0,
        peak_pnl_pct=0.0,
        bins_out_of_range=0,
        minutes_oor=0.0,
        age_minutes=0.0,
        fee_per_tvl_24h=None,
    )
    base.update(kw)
    return PositionView(**base)


# ---------------------------------------------------------------------------
# Exit doctrine (pure)


def test_stop_loss_triggers():
    d = evaluate_exit(view(pnl_pct=-25.0), RULES)
    assert (d.action, d.reason) == ("close", "stop_loss")


def test_take_profit_triggers():
    d = evaluate_exit(view(pnl_pct=5.0), RULES)
    assert (d.action, d.reason) == ("close", "take_profit")


def test_trailing_tp_after_giveback():
    assert evaluate_exit(view(pnl_pct=2.4, peak_pnl_pct=4.0), RULES).reason == "trailing_tp"
    assert evaluate_exit(view(pnl_pct=3.0, peak_pnl_pct=4.0), RULES).action == "hold"


def test_oor_requires_bins_and_grace():
    assert evaluate_exit(view(bins_out_of_range=10, minutes_oor=30.0), RULES).reason == "out_of_range"
    assert evaluate_exit(view(bins_out_of_range=9, minutes_oor=999.0), RULES).action == "hold"
    assert evaluate_exit(view(bins_out_of_range=10, minutes_oor=5.0), RULES).action == "hold"


def test_yield_floor_needs_age_and_data():
    assert (
        evaluate_exit(view(age_minutes=61, fee_per_tvl_24h=6.9), RULES).reason
        == "yield_floor"
    )
    assert evaluate_exit(view(age_minutes=30, fee_per_tvl_24h=1.0), RULES).action == "hold"
    # Missing fee data never triggers the floor.
    assert evaluate_exit(view(age_minutes=999), RULES).action == "hold"


# ---------------------------------------------------------------------------
# Lifecycle integration


def _seed_candidate(db, pool="PoolLife", score=90.0):
    db.add(
        MeteoraCandidate(
            cycle_id="cyc-test",
            pool_address=pool,
            name="LIFE-SOL",
            degen_score=score,
            rejected=False,
            signal_snapshot={"organic_score": 80},
        )
    )
    db.commit()


def test_open_logs_deploy_decision(db):
    _seed_candidate(db)
    pos = open_paper_position(
        pool_address="PoolLife",
        pool_name="LIFE-SOL",
        strategy="bid_ask",
        side="bid",
        bins_below=40,
        bins_above=40,
        bin_step=100.0,
        lower_price=90.0,
        upper_price=110.0,
        amount_sol=1.0,
        entry_price=100.0,
        signal_snapshot={"organic_score": 80},
        cycle_id="cyc-test",
        session=db,
    )
    assert pos.id and pos.status == "open"
    dec = (
        db.query(MeteoraDecision)
        .filter_by(position_id=pos.id, action="deploy")
        .one()
    )
    assert dec.actor == "paper_manager"


@pytest.mark.asyncio
async def test_management_cycle_closes_on_take_profit(db, monkeypatch):
    _seed_candidate(db)
    pos = open_paper_position(
        pool_address="PoolLife",
        pool_name="LIFE-SOL",
        strategy="spot",
        side="two_sided",
        bins_below=20,
        bins_above=20,
        bin_step=100.0,
        lower_price=95.0,
        upper_price=105.0,
        amount_sol=2.0,
        entry_price=100.0,
        signal_snapshot={},
        cycle_id="cyc-test",
        session=db,
    )

    async def fake_price(pool_address):
        return 106.0  # +6% over midpoint ⇒ TP fires

    summary = await run_management_with_db(price_fetch=fake_price)
    assert summary["closed"] == 1
    db.expire_all()
    fresh = db.get(MeteoraPosition, pos.id)
    assert fresh.status == "closed"
    assert fresh.close_reason == "take_profit"
    closes = (
        db.query(MeteoraDecision)
        .filter_by(position_id=pos.id, action="close")
        .all()
    )
    assert len(closes) == 1


@pytest.mark.asyncio
async def test_management_cycle_holds_inside_range(db):
    _seed_candidate(db)
    open_paper_position(
        pool_address="PoolHold",
        pool_name="HOLD-SOL",
        strategy="spot",
        side="two_sided",
        bins_below=20,
        bins_above=20,
        bin_step=100.0,
        lower_price=90.0,
        upper_price=110.0,
        amount_sol=1.0,
        entry_price=100.0,
        signal_snapshot={},
        cycle_id="cyc-test",
        session=db,
    )

    async def fake_price(pool_address):
        return 101.0

    summary = await run_management_with_db(price_fetch=fake_price)
    assert summary["holds"] == 1 and summary["closed"] == 0


async def run_management_with_db(price_fetch):
    from backend.data.meteora.paper import run_management_cycle

    return await run_management_cycle(price_fetch=price_fetch)


def test_ooo_cooldown_armed_after_third_oor_close(db):
    for i in range(3):
        pos = open_paper_position(
            pool_address="PoolOOR",
            pool_name="OOR-SOL",
            strategy="spot",
            side="two_sided",
            bins_below=20,
            bins_above=20,
            bin_step=100.0,
            lower_price=90.0,
            upper_price=110.0,
            amount_sol=1.0,
            entry_price=100.0,
            signal_snapshot={},
            cycle_id="cyc",
            session=db,
        )
        close_paper_position(
            pos,
            exit_price=80.0,
            fees_earned_usd=0.0,
            reason="out_of_range",
            session=db,
        )
    rows = (
        db.query(MeteoraCooldown)
        .filter_by(scope="pool", target="PoolOOR", trigger="oor_cooldown")
        .all()
    )
    assert len(rows) == 1 and rows[0].event_count >= 1


# ---------------------------------------------------------------------------
# Darwin learning


def _mk_closed(idx, pnl, snapshot, db):
    pos = MeteoraPosition(
        mode="paper",
        strategy="spot",
        side="two_sided",
        pool_address=f"P{idx}",
        pool_name=f"N{idx}",
        status="closed",
        lower_price=90.0,
        upper_price=110.0,
        amount_sol=1.0,
        initial_value_usd=100.0,
        signal_snapshot=snapshot,
        pnl_pct=pnl,
        fees_earned_usd=0.0,
        final_value_usd=100.0 * (1 + pnl / 100),
        opened_at=datetime.now(UTC) - timedelta(hours=2),
        closed_at=datetime.now(UTC),
        close_reason="take_profit" if pnl > 0 else "stop_loss",
    )
    db.add(pos)
    db.flush()
    return pos


def test_weights_boost_win_correlated_signal(db):
    # organic_score present in ALL winners, absent in all losers.
    for i in range(4):
        _mk_closed(i, 8.0, {"organic_score": 70}, db)
    for i in range(4, 8):
        _mk_closed(i, -8.0, {}, db)
    weights = recalc_signal_weights(db)
    assert weights["organic_score"] > 1.0
    row = (
        db.query(MeteoraSignalWeight)
        .filter_by(signal_name="organic_score")
        .one()
    )
    assert row.weight == weights["organic_score"]


def test_weights_decay_loss_correlated_signal_and_clamp(db):
    db.add(MeteoraSignalWeight(signal_name="volatility", weight=FLOOR / 0.95))
    db.commit()
    # volatility present only in losers.
    for i in range(3):
        _mk_closed(f"L{i}", -9.0, {"volatility": 5}, db)
    for i in range(3, 6):
        _mk_closed(f"W{i}", 9.0, {}, db)
    weights = recalc_signal_weights(db)
    assert weights["volatility"] <= FLOOR + 1e-9  # clamped at floor
    row = (
        db.query(MeteoraSignalWeight)
        .filter_by(signal_name="volatility")
        .one()
    )
    assert row.weight == pytest.approx(FLOOR)


def test_weight_respects_ceiling(db):
    from backend.models.meteora_db import MeteoraSignalWeight

    db.add(MeteoraSignalWeight(signal_name="holder_count", weight=CEILING / 1.05))
    db.commit()
    for i in range(3):
        _mk_closed(f"H{i}", 7.0, {"holder_count": 900}, db)
    for i in range(3, 6):
        _mk_closed(f"Hn{i}", -7.0, {}, db)
    weights = recalc_signal_weights(db)
    assert weights["holder_count"] >= CEILING - 1e-9


def test_derive_lesson_skips_noise_band(db):
    pos = _mk_closed("nz", 1.0, {"organic_score": 50}, db)
    assert derive_lesson(db, pos) is None
    pos2 = _mk_closed("big", -12.0, {"organic_score": 50}, db)
    lesson = derive_lesson(db, pos2)
    assert lesson is not None and lesson.kind == "negative"
    assert len(lesson.text) <= 400


def test_should_recalc_on_multiples_of_five(db):
    assert not should_recalc(db)
    for i in range(5):
        _mk_closed(f"S{i}", 5.0, {}, db)
    assert should_recalc(db)
