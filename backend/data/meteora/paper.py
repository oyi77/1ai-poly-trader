"""Meteora paper agent — deterministic management loop with Meridian's exit
doctrine, decision log, and cooldown automation. No LLM in the loop.

Exit rules ported from meridian user-config defaults, with the stop-loss
tightened to -25% until our own closed-position data justifies loosening:
- close after `oor_bins` consecutive evaluation bins out-of-range plus grace
- pool cooldown after repeated OOR-triggered closes
- hard stop-loss / take-profit / trailing take-profit on PnL%
- yield floor: fee/TVL(24h) below threshold after minimum age ⇒ close
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from backend.data.meteora.screening import (
    record_cooldown,
)

BIN_STEP_BPS_DEFAULT = 100.0


@dataclass(frozen=True)
class ExitRules:
    stop_loss_pct: float = -25.0
    take_profit_pct: float = 5.0
    trailing_trigger_pct: float = 3.0
    trailing_drop_pct: float = 1.5
    oor_bins_to_close: int = 10
    oor_wait_minutes: int = 30
    oor_cooldown_count: int = 3
    oor_cooldown_hours: float = 12.0
    min_fee_per_tvl_24h: float = 7.0
    min_age_minutes_for_yield: int = 60


@dataclass
class PositionView:
    """Everything the exit engine may look at — no ORM inside the engine."""

    pnl_pct: float
    peak_pnl_pct: float
    bins_out_of_range: int
    minutes_oor: float
    age_minutes: float
    fee_per_tvl_24h: float | None


@dataclass
class ExitDecision:
    action: str          # hold | close
    reason: str          # hold | stop_loss | take_profit | trailing_tp |
    #                        out_of_range | yield_floor
    detail: str = ""


def evaluate_exit(view: PositionView, rules: ExitRules) -> ExitDecision:
    """Pure exit doctrine — ordered cheapest-signal first."""
    if view.pnl_pct <= rules.stop_loss_pct:
        return ExitDecision("close", "stop_loss", f"pnl {view.pnl_pct:.2f}%")
    if view.pnl_pct >= rules.take_profit_pct:
        return ExitDecision("close", "take_profit", f"pnl {view.pnl_pct:.2f}%")
    if (
        view.peak_pnl_pct >= rules.trailing_trigger_pct
        and view.pnl_pct <= view.peak_pnl_pct - rules.trailing_drop_pct
    ):
        return ExitDecision(
            "close",
            "trailing_tp",
            f"peak {view.peak_pnl_pct:.2f}% → {view.pnl_pct:.2f}%",
        )
    if (
        view.bins_out_of_range >= rules.oor_bins_to_close
        and view.minutes_oor >= rules.oor_wait_minutes
    ):
        return ExitDecision(
            "close",
            "out_of_range",
            f"{view.bins_out_of_range} bins OOR for {view.minutes_oor:.0f}m",
        )
    if (
        view.age_minutes >= rules.min_age_minutes_for_yield
        and view.fee_per_tvl_24h is not None
        and view.fee_per_tvl_24h < rules.min_fee_per_tvl_24h
    ):
        return ExitDecision(
            "close",
            "yield_floor",
            f"fee/tvl24h {view.fee_per_tvl_24h:.2f} < {rules.min_fee_per_tvl_24h}",
        )
    return ExitDecision("hold", "hold")


# ---------------------------------------------------------------------------
# DB-facing helpers (lazy SessionLocal per repo test convention)


def _session_local():
    from backend.models.database import SessionLocal

    return SessionLocal()


def _utc(dt):
    """Coerce possibly-naive SQLite datetimes to aware UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _bins_distance(entry_price: float, current_price: float, bin_step: float) -> int:
    step = 1.0 + bin_step / 10_000.0
    if entry_price <= 0 or current_price <= 0:
        return 0
    return abs(round(__import__("math").log(current_price / entry_price, step)))


def open_paper_position(
    *,
    pool_address: str,
    pool_name: str,
    strategy: str,
    side: str,
    bins_below: int,
    bins_above: int,
    bin_step: float,
    lower_price: float,
    upper_price: float,
    amount_sol: float,
    entry_price: float,
    signal_snapshot: dict[str, Any] | None = None,
    cycle_id: str | None = None,
    session=None,
):
    """Create a paper position row + deploy decision; returns the row."""
    from backend.models.meteora_db import MeteoraDecision, MeteoraPosition

    own = session is None
    s = session or _session_local()
    try:
        pos = MeteoraPosition(
            mode="paper",
            strategy=strategy,
            side=side,
            pool_address=pool_address,
            pool_name=pool_name,
            status="open",
            bins_below=bins_below,
            bins_above=bins_above,
            bin_step=bin_step,
            lower_price=min(lower_price, upper_price),
            upper_price=max(lower_price, upper_price),
            amount_sol=amount_sol,
            initial_value_usd=amount_sol * entry_price,
            signal_snapshot=signal_snapshot or {},
            entry_cycle_id=cycle_id,
            opened_at=datetime.now(UTC),
        )
        s.add(pos)
        s.flush()
        s.add(
            MeteoraDecision(
                actor="paper_manager",
                action="deploy",
                pool_address=pool_address,
                position_id=pos.id,
                mode="paper",
                summary=f"Opened {strategy}/{side} paper LP on {pool_name}",
                reason="screened candidate above threshold",
                metrics={"entry_price": entry_price, "amount_sol": amount_sol},
                alternatives_considered=[],
            )
        )
        s.commit()
        logger.info(f"[meteora-paper] opened #{pos.id} {pool_name} {strategy}/{side}")
        return pos
    except Exception:
        s.rollback()
        raise
    finally:
        if own:
            s.close()


def close_paper_position(
    pos,
    *,
    exit_price: float,
    fees_earned_usd: float,
    reason: str,
    session=None,
) -> None:
    """Close a paper position, log the decision, and arm OOR cooldowns."""
    from backend.data.meteora.learning import derive_lesson
    from backend.models.meteora_db import MeteoraDecision

    own = session is None
    s = session or _session_local()
    try:
        now = datetime.now(UTC)
        held = max(0, int((now - _utc(pos.opened_at)).total_seconds() // 60)) if pos.opened_at else 0
        mid = (pos.lower_price + pos.upper_price) / 2.0 if pos.lower_price and pos.upper_price else exit_price
        final_value = (
            pos.initial_value_usd * (exit_price / mid)
            if mid and pos.initial_value_usd is not None
            else None
        )
        pnl_pct = ((final_value + fees_earned_usd) / pos.initial_value_usd - 1.0) * 100.0 if pos.initial_value_usd else 0.0

        pos.status = "closed"
        pos.closed_at = now
        pos.close_reason = reason
        pos.fees_earned_usd = fees_earned_usd
        pos.final_value_usd = final_value
        pos.pnl_pct = pnl_pct
        pos.minutes_held = held
        s.add(
            MeteoraDecision(
                actor="paper_manager",
                action="close",
                pool_address=pos.pool_address,
                position_id=pos.id,
                mode="paper",
                summary=f"Closed #{pos.id} ({reason})",
                reason=reason,
                metrics={
                    "exit_price": exit_price,
                    "fees_usd": fees_earned_usd,
                    "pnl_pct": pnl_pct,
                    "minutes_held": held,
                },
                alternatives_considered=[],
            )
        )
        s.flush()
        derive_lesson(s, pos)
        if reason == "out_of_range":
            count = (
                s.query(MeteoraDecision)
                .filter(
                    MeteoraDecision.action == "close",
                    MeteoraDecision.pool_address == pos.pool_address,
                    MeteoraDecision.reason == "out_of_range",
                )
                .count()
            )
            rules = ExitRules()
            if count % rules.oor_cooldown_count == 0:
                record_cooldown(
                    s,
                    scope="pool",
                    target=pos.pool_address,
                    trigger="oor_cooldown",
                    hours=rules.oor_cooldown_hours,
                )
        s.commit()
        logger.info(
            f"[meteora-paper] closed #{pos.id} {pos.pool_name} ({reason}) "
            f"pnl={pnl_pct:.2f}%"
        )
    except Exception:
        s.rollback()
        raise
    finally:
        if own:
            s.close()


async def run_management_cycle(
    *,
    rules: ExitRules | None = None,
    price_fetch=None,
    session=None,
) -> dict[str, Any]:
    """Evaluate all open paper positions; execute exits that trigger.

    price_fetch: async fn(pool_address) -> float. Defaults to the DLMM API.
    """
    from backend.models.meteora_db import MeteoraPosition

    r = rules or ExitRules()
    own = session is None
    s = session or _session_local()

    # --- Zombie sweep: crash between "closing" mark and close commit leaves
    # rows stuck mid-transition; force-close anything stale (>10 min).
    try:
        cutoff = datetime.now(UTC) - timedelta(minutes=10)
        zombies = (
            s.query(MeteoraPosition)
            .filter(
                MeteoraPosition.mode == "paper",
                MeteoraPosition.status == "closing",
                MeteoraPosition.opened_at <= cutoff,
            )
            .all()
        )
        for z in zombies:
            close_paper_position(
                z, exit_price=z.upper_price or 0.0,
                fees_earned_usd=0.0, reason="recovered", session=s,
            )
        if zombies:
            logger.warning(f"[meteora-paper] recovered {len(zombies)} zombie closing positions")
    except Exception as exc:
        logger.error(f"[meteora-paper] zombie sweep failed: {exc}")
        s.rollback()

    try:
        open_positions = (
            s.query(MeteoraPosition)
            .filter(MeteoraPosition.mode == "paper", MeteoraPosition.status == "open")
            .all()
        )
    finally:
        if own:
            s.close()
    ids = [p.id for p in open_positions]

    summary = {"evaluated": len(ids), "closed": 0, "holds": 0}
    fetch = price_fetch or _default_price_fetch
    for pid in ids:
        s = session or _session_local()
        try:
            pos = s.get(MeteoraPosition, pid)
            if not pos or pos.status != "open":
                continue
            price = await fetch(pos.pool_address)
            if not price:
                continue
            step_bps = pos.bin_step or BIN_STEP_BPS_DEFAULT
            bins_out = _bins_distance(
                (pos.lower_price + pos.upper_price) / 2.0, price, step_bps
            )
            in_range = pos.lower_price <= price <= pos.upper_price
            if in_range:
                bins_out = 0
            pnl_pct = (
                (price / ((pos.lower_price + pos.upper_price) / 2.0) - 1.0) * 100.0
                if pos.lower_price and pos.upper_price
                else 0.0
            )
            snap = pos.signal_snapshot or {}
            peak = max(float(snap.get("peak_pnl_pct") or 0.0), pnl_pct)
            age_min = (
                (datetime.now(UTC) - _utc(pos.opened_at)).total_seconds() / 60.0
                if pos.opened_at
                else 0.0
            )
            decision = evaluate_exit(
                PositionView(
                    pnl_pct=pnl_pct,
                    peak_pnl_pct=peak,
                    bins_out_of_range=bins_out,
                    minutes_oor=(bins_out / max(1, r.oor_bins_to_close))
                    * r.oor_wait_minutes,
                    age_minutes=age_min,
                    fee_per_tvl_24h=snap.get("fee_per_tvl_24h"),
                ),
                r,
            )
            snap["peak_pnl_pct"] = peak
            pos.signal_snapshot = snap

            if decision.action == "close":
                pos.status = "closing"  # guard against double-processing
                s.commit()
                await close_paper_position_async(
                    pos.id, exit_price=price, reason=decision.reason
                )
                summary["closed"] += 1
            else:
                s.commit()
                summary["holds"] += 1
        except Exception as exc:
            logger.exception(f"[meteora-paper] management error on #{pid}: {exc}")
            if own is False and s.in_transaction():
                s.rollback()
    logger.info(f"[meteora-paper] management cycle: {summary}")
    return summary


async def close_paper_position_async(position_id: int, *, exit_price: float, reason: str):
    def _work():
        session = _session_local()
        try:
            from backend.models.meteora_db import MeteoraPosition

            pos = session.get(MeteoraPosition, position_id)
            close_paper_position(
                pos, exit_price=exit_price, fees_earned_usd=0.0, reason=reason,
                session=session,
            )
        finally:
            session.close()

    await asyncio.to_thread(_work)


async def _default_price_fetch(pool_address: str) -> float | None:
    from backend.data.meteora.client import get_dlmm_client

    pool = await get_dlmm_client().get_pool(pool_address)
    if not pool:
        return None
    price = pool.get("current_price")
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return None


async def meteora_management_job() -> None:
    """APScheduler-compatible management entrypoint (every 10 minutes)."""
    try:
        await run_management_cycle()
    except Exception as exc:
        logger.exception(f"[meteora-paper] management job failed: {exc}")
