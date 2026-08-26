"""Meteora screening service — orchestrates fetch → screen → persist cycles.
DB sessions are resolved lazily inside functions so tests (which swap
SessionLocal on backend.models.database at runtime) always observe the current
binding.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from backend.data.meteora.client import get_discovery_client
from backend.data.meteora.screening import (
    ScreeningFilters,
    _get_nested,
    get_active_cooldowns,
    screen_pools,
)


def _default_filters() -> ScreeningFilters:
    return ScreeningFilters()


def _f(value: Any) -> float | None:
    try:
        n = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return n if n is not None and n == n else None


def _i(value: Any) -> int | None:
    n = _f(value)
    return int(n) if n is not None else None


def _persist_cycle(
    cycle_id: str,
    pools: list[dict[str, Any]],
    results: list,
    *,
    timeframe: str,
) -> None:
    """Write snapshot + candidate rows for one completed cycle."""
    from backend.models.database import SessionLocal
    from backend.models.meteora_db import MeteoraCandidate, MeteoraPoolSnapshot

    session = SessionLocal()
    try:
        now = datetime.now(UTC)
        for pool in pools:
            address = str(pool.get("pool_address") or "")
            base = pool.get("token_x") or {}
            quote = pool.get("token_y") or {}
            session.add(
                MeteoraPoolSnapshot(
                    cycle_id=cycle_id,
                    pool_address=address,
                    name=str(pool.get("name") or ""),
                    active_tvl=_f(_get_nested(pool, "active_tvl", "tvl")),
                    fee_active_tvl_ratio=_f(pool.get("fee_active_tvl_ratio")),
                    volume_active_tvl_ratio=_f(pool.get("volume_active_tvl_ratio")),
                    unique_lps=_f(pool.get("unique_lps")),
                    positions_created=_f(pool.get("positions_created")),
                    volatility=_f(pool.get("volatility")),
                    base_token_holders=_i(
                        pool.get("base_token_holders") or base.get("holders")
                    ),
                    organic_score=_f(base.get("organic_score")),
                    quote_organic_score=_f(quote.get("organic_score")),
                    market_cap=_f(base.get("market_cap")),
                    launchpad=base.get("launchpad"),
                    bin_step=_f(_get_nested(pool, "dlmm_params.bin_step", "bin_step")),
                    payload=pool,
                    captured_at=now,
                )
            )
        for r in results:
            score = r.degen_score if not r.rejected else 0.0
            subs = r.subscores if not r.rejected else {}
            session.add(
                MeteoraCandidate(
                    cycle_id=cycle_id,
                    pool_address=r.pool_address,
                    name=r.name,
                    degen_score=score,
                    weighted_score=(r.signal_snapshot or {}).get("weighted_score"),
                    sub_trading=subs.get("trading"),
                    sub_lp=subs.get("lp"),
                    sub_fees=subs.get("fees"),
                    sub_liquidity=subs.get("liquidity"),
                    rejected=r.rejected,
                    reject_reason=r.reject_reason,
                    signal_snapshot=r.signal_snapshot,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def run_screening_cycle(
    *,
    timeframe: str = "30m",
    category: str = "trending",
    page_size: int = 100,
    filters: ScreeningFilters | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """One screening pass: discover → filter/score → persist → summarize."""
    from backend.data.meteora.screening import SIGNAL_NAMES
    from backend.models.database import SessionLocal
    from backend.models.meteora_db import MeteoraSignalWeight

    f = filters or _default_filters()
    cycle_id = f"scr-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    pools = await get_discovery_client().fetch_pools(
        page_size=min(page_size, 500), timeframe=timeframe, category=category
    )
    logger.info(
        f"[meteora] cycle {cycle_id}: fetched {len(pools)} pools "
        f"({category}/{timeframe})"
    )

    # Darwin weights + cooldowns come from DB (sync I/O off the event loop).
    def _load_db_state() -> tuple[dict[str, float], set[tuple[str, str]]]:
        session = SessionLocal()
        try:
            weights = {
                w.signal_name: w.weight
                for w in session.query(MeteoraSignalWeight).all()
            }
            return weights, get_active_cooldowns(session)
        finally:
            session.close()

    weights, cooldowns = await asyncio.to_thread(_load_db_state)

    results = screen_pools(
        pools,
        filters=f,
        timeframe=timeframe,
        signal_weights={k: v for k, v in weights.items() if k in SIGNAL_NAMES},
        cooldown_targets=cooldowns,
    )

    if persist and pools:
        await asyncio.to_thread(
            _persist_cycle, cycle_id, pools, results, timeframe=timeframe
        )

    accepted = [r for r in results if not r.rejected]
    summary = {
        "cycle_id": cycle_id,
        "screened": len(results),
        "rejected": len(results) - len(accepted),
        "accepted": len(accepted),
        "top": [
            {
                "pool_address": r.pool_address,
                "name": r.name,
                "degen_score": round(r.degen_score, 2),
                "subscores": {k: round(v, 3) for k, v in r.subscores.items()},
            }
            for r in accepted[:10]
        ],
    }
    logger.info(
        f"[meteora] cycle {cycle_id}: {summary['accepted']} accepted / "
        f"{summary['rejected']} rejected"
    )
    return summary


async def meteora_screening_job() -> None:
    """APScheduler-compatible periodic screening entrypoint (every 30 min)."""
    try:
        await run_screening_cycle()
    except Exception as exc:
        logger.exception(f"[meteora] screening job failed: {exc}")


def prune_expired_data(session, *, days: int | None = None) -> dict[str, int]:
    """Delete snapshot/candidate/decision rows older than the retention window."""
    from datetime import timedelta

    from backend.config import settings as cfg
    from backend.models.meteora_db import (
        MeteoraCandidate,
        MeteoraDecision,
        MeteoraPoolSnapshot,
    )

    days = days or getattr(cfg, "METEORA_RETENTION_DAYS", 30)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    counts: dict[str, int] = {}
    try:
        counts["snapshots"] = (
            session.query(MeteoraPoolSnapshot)
            .filter(MeteoraPoolSnapshot.captured_at < cutoff)
            .delete()
        )
        counts["candidates"] = (
            session.query(MeteoraCandidate)
            .filter(MeteoraCandidate.created_at < cutoff)
            .delete()
        )
        counts["decisions"] = (
            session.query(MeteoraDecision)
            .filter(MeteoraDecision.created_at < cutoff)
            .delete()
        )
        session.commit()
        logger.info(f"[meteora] retention pruned {counts} (>{days}d)")
        return counts
    except Exception:
        session.rollback()
        raise


async def meteora_retention_job() -> None:
    """APScheduler daily retention entrypoint."""
    from backend.models.database import SessionLocal

    session = SessionLocal()
    try:
        await asyncio.to_thread(prune_expired_data, session)
    finally:
        session.close()
