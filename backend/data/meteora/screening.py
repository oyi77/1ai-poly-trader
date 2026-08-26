"""Meteora DLMM pool screening — Degen Score port + hard filters.

Pure functions first (score/filter), orchestration second (DB cooldowns,
candidate persistence live in the agent layer). The Degen Score is a verbatim
port of Meridian's geometric-mean scorer (tools/screening.js): a pool must be
balanced across trading activity, LP activity, fee yield, and liquidity depth
— spiking any single metric cannot dominate the score.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from backend.models.meteora_db import MeteoraCooldown

TIMEFRAME_MINUTES = {
    "5m": 5,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "12h": 720,
    "24h": 1440,
}
DEGEN_REFERENCE_MINUTES = 30

# Signal names tracked by the darwin loop; weights multiply sub-scores' inputs.
SIGNAL_NAMES = (
    "organic_score",
    "fee_tvl_ratio",
    "volume",
    "market_cap",
    "holder_count",
    "volatility",
    "unique_lps",
    "positions_created",
)


@dataclass
class DegenTargets:
    """Sub-score saturation points, expressed per 30-minute reference window."""

    target_vol_ratio: float = 20.0     # volume/active_tvl for full trading score
    target_lp_count: float = 40.0      # unique_lps + positions_created
    target_fee_ratio: float = 0.20     # fee/active_tvl
    target_liquidity: float = 20000.0  # active_tvl ($) floor — not time-scaled


@dataclass
class ScreeningFilters:
    """Hard gates applied before scoring. None/absent checks skip gracefully."""

    min_tvl: float = 50_000.0          # stricter than Meridian default at start
    max_tvl: float | None = None
    min_volume: float = 500.0
    min_organic: float = 60.0          # base token organic score
    min_quote_organic: float = 60.0    # quote token organic score
    min_market_cap: float | None = 150_000.0
    max_market_cap: float | None = 100_000_000.0
    min_bin_step: float = 80.0
    max_bin_step: float = 125.0
    min_fee_active_tvl_ratio: float = 0.05
    min_holders: int = 1000            # stricter than Meridian default at start
    max_bot_holders_pct: float | None = 30.0   # applied only when field present
    max_top10_pct: float | None = 60.0         # applied only when field present
    blocked_launchpads: set[str] = field(default_factory=set)
    allowed_launchpads: set[str] = field(default_factory=set)  # empty = allow all


@dataclass
class ScreenResult:
    pool_address: str
    name: str
    rejected: bool
    reject_reason: str | None
    degen_score: float
    subscores: dict[str, float]
    signal_snapshot: dict[str, Any]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x)) if math.isfinite(x) else 0.0


def _get_nested(pool: dict, *paths: str) -> Any:
    """First non-null value among dotted paths, e.g. ('dlmm_params.bin_step',)."""
    for path in paths:
        node: Any = pool
        for part in path.split("."):
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(part)
        if node is not None:
            return node
    return None


def degen_score(
    pool: dict[str, Any],
    *,
    timeframe: str = "30m",
    targets: DegenTargets | None = None,
) -> tuple[float, dict[str, float]]:
    """Geometric-mean efficiency score on 0..100 with per-metric subscores.

    Returns (score, {"trading": .., "lp": .., "fees": .., "liquidity": ..}).
    Score is 0 unless every sub-score is > 0.
    """
    t = targets or DegenTargets()
    la = _num(_get_nested(pool, "active_tvl", "tvl")) or 0.0
    if la <= 0:
        return 0.0, {"trading": 0.0, "lp": 0.0, "fees": 0.0, "liquidity": 0.0}

    tf_minutes = TIMEFRAME_MINUTES.get(timeframe, DEGEN_REFERENCE_MINUTES)
    tf_scale = DEGEN_REFERENCE_MINUTES / tf_minutes

    # Trading: prefer precomputed ratio, else volume/tvl, window-normalized.
    vol_ratio = _num(pool.get("volume_active_tvl_ratio"))
    volume_window = _num(pool.get("volume")) or _num(pool.get("volume_window")) or 0.0
    trading_ratio = (
        vol_ratio if vol_ratio is not None else volume_window / la
    ) * tf_scale

    # Fees: same pattern.
    fee_ratio = _num(pool.get("fee_active_tvl_ratio"))
    fee_window = _num(pool.get("fee")) or _num(pool.get("fee_window")) or 0.0
    fees_ratio = (fee_ratio if fee_ratio is not None else fee_window / la) * tf_scale

    lp_activity = (
        (_num(pool.get("unique_lps")) or 0.0)
        + (_num(pool.get("positions_created")) or 0.0)
    ) * tf_scale

    s_trading = _clamp01(trading_ratio / t.target_vol_ratio)
    s_lp = _clamp01(lp_activity / t.target_lp_count)
    s_fees = _clamp01(fees_ratio / t.target_fee_ratio)
    s_liq = _clamp01(math.log10(la) / math.log10(t.target_liquidity))

    subs = {"trading": s_trading, "lp": s_lp, "fees": s_fees, "liquidity": s_liq}
    product = s_trading * s_lp * s_fees * s_liq
    score = (product**0.25) * 100 if product > 0 else 0.0
    return score, subs


def build_signal_snapshot(pool: dict[str, Any], timeframe: str) -> dict[str, Any]:
    """Entry-time signal values stored with candidates/positions for darwin."""
    base = pool.get("token_x") or {}
    quote = pool.get("token_y") or {}
    return {
        "timeframe": timeframe,
        "organic_score": _num(base.get("organic_score")),
        "quote_organic_score": _num(quote.get("organic_score")),
        "fee_tvl_ratio": _num(pool.get("fee_active_tvl_ratio")),
        "volume": _num(pool.get("volume")),
        "market_cap": _num(base.get("market_cap")),
        "holder_count": _num(
            pool.get("base_token_holders") or base.get("holders")
        ),
        "volatility": _num(pool.get("volatility")),
        "unique_lps": _num(pool.get("unique_lps")),
        "positions_created": _num(pool.get("positions_created")),
        "entry_active_tvl": _num(_get_nested(pool, "active_tvl", "tvl")),
    }


def passes_hard_filters(
    pool: dict[str, Any], f: ScreeningFilters
) -> tuple[bool, str | None]:
    pool_type = pool.get("pool_type")
    if pool_type is not None and str(pool_type).lower() != "dlmm":
        return False, f"pool_type {pool_type} not supported"
    bin_step_early = _num(_get_nested(pool, "dlmm_params.bin_step", "bin_step"))
    if bin_step_early is None:
        return False, "bin_step missing"

    tvl = _num(_get_nested(pool, "active_tvl", "tvl"))
    if tvl is None or tvl < f.min_tvl:
        return False, f"tvl {tvl} < {f.min_tvl}"
    if f.max_tvl is not None and tvl > f.max_tvl:
        return False, f"tvl {tvl} > {f.max_tvl}"

    volume = _num(pool.get("volume"))
    if volume is not None and volume < f.min_volume:
        return False, f"volume {volume} < {f.min_volume}"

    base = pool.get("token_x") or {}
    quote = pool.get("token_y") or {}
    organic = _num(base.get("organic_score"))
    if organic is not None and organic < f.min_organic:
        return False, f"base organic {organic} < {f.min_organic}"
    quote_organic = _num(quote.get("organic_score"))
    if quote_organic is not None and quote_organic < f.min_quote_organic:
        return False, f"quote organic {quote_organic} < {f.min_quote_organic}"

    mcap = _num(base.get("market_cap"))
    if f.min_market_cap is not None and (mcap is None or mcap < f.min_market_cap):
        return False, f"mcap {mcap} < {f.min_market_cap}"
    if f.max_market_cap is not None and mcap is not None and mcap > f.max_market_cap:
        return False, f"mcap {mcap} > {f.max_market_cap}"

    bin_step = _num(_get_nested(pool, "dlmm_params.bin_step", "bin_step"))
    if bin_step is None:
        return False, "bin_step missing"
    if bin_step < f.min_bin_step or bin_step > f.max_bin_step:
        return False, f"bin_step {bin_step} outside [{f.min_bin_step}, {f.max_bin_step}]"

    fee_ratio = _num(pool.get("fee_active_tvl_ratio"))
    if fee_ratio is not None and fee_ratio < f.min_fee_active_tvl_ratio:
        return False, f"fee/active_tvl {fee_ratio} < {f.min_fee_active_tvl_ratio}"

    holders = _num(pool.get("base_token_holders") or base.get("holders"))
    if holders is None or holders < f.min_holders:
        return False, f"holders {holders} < {f.min_holders}"

    bot_pct = _num(_get_nested(pool, "bot_holders_pct", "base_token_bot_pct"))
    if f.max_bot_holders_pct is not None and bot_pct is not None and bot_pct > f.max_bot_holders_pct:
        return False, f"bot holders {bot_pct}% > {f.max_bot_holders_pct}%"

    top10 = _num(_get_nested(pool, "top10_holders_pct", "base_token_top10_pct"))
    if f.max_top10_pct is not None and top10 is not None and top10 > f.max_top10_pct:
        return False, f"top10 supply {top10}% > {f.max_top10_pct}%"

    launchpad = _get_nested(
        pool,
        "launchpad",
        "token_x.launchpad",
        "token_x.launchpad_platform",
    )
    if launchpad and str(launchpad) in f.blocked_launchpads:
        return False, f"launchpad {launchpad} blocked"
    if f.allowed_launchpads and launchpad and str(launchpad) not in f.allowed_launchpads:
        return False, f"launchpad {launchpad} not allowlisted"

    return True, None


def screen_pools(
    pools: list[dict[str, Any]],
    *,
    filters: ScreeningFilters,
    timeframe: str = "30m",
    targets: DegenTargets | None = None,
    signal_weights: dict[str, float] | None = None,
    cooldown_targets: set[tuple[str, str]] | None = None,
) -> list[ScreenResult]:
    """Score + filter a page of discovery pools.

    cooldown_targets: set of (scope, address) currently cooling down
    ("pool" scope matches pool_address, "base_mint" matches token_x.address).
    """
    weights = signal_weights or {}
    cool = cooldown_targets or set()
    results: list[ScreenResult] = []

    for pool in pools:
        address = str(pool.get("pool_address") or "")
        name = str(pool.get("name") or "")
        snapshot = build_signal_snapshot(pool, timeframe)

        base_mint = str((pool.get("token_x") or {}).get("address") or "")
        on_cooldown = ("pool", address) in cool or (
            base_mint and ("base_mint", base_mint) in cool
        )
        if on_cooldown:
            results.append(
                ScreenResult(address, name, True, "cooldown active", 0.0, {}, snapshot)
            )
            continue

        ok, reason = passes_hard_filters(pool, filters)
        if not ok:
            results.append(
                ScreenResult(address, name, True, reason, 0.0, {}, snapshot)
            )
            continue

        score, subs = degen_score(pool, timeframe=timeframe, targets=targets)
        weighted = apply_signal_weights(snapshot, weights, base_score=score)
        results.append(
            ScreenResult(address, name, False, None, score, subs, snapshot)
        )
        results[-1].signal_snapshot["weighted_score"] = weighted

    results.sort(key=lambda r: r.degen_score, reverse=True)
    return results


def apply_signal_weights(
    snapshot: dict[str, Any],
    weights: dict[str, float],
    *,
    base_score: float,
) -> float:
    """Darwin-weighted score: neutral (1.0) weights leave the score unchanged.

    Each signal contributes its normalized weight factor; the final multiplier
    is the mean of available weight factors so sparse snapshots stay stable.
    """
    factors = [
        weights[name]
        for name in SIGNAL_NAMES
        if snapshot.get(name) is not None and weights.get(name) is not None
    ]
    multiplier = sum(factors) / len(factors) if factors else 1.0
    return base_score * multiplier


# ---------------------------------------------------------------------------
# Cooldown helpers (DB-backed)


def get_active_cooldowns(session) -> set[tuple[str, str]]:
    now = datetime.now(UTC)
    rows = (
        session.query(MeteoraCooldown)
        .filter(MeteoraCooldown.expires_at > now)
        .all()
    )
    return {(r.scope, r.target) for r in rows}


def record_cooldown(
    session,
    *,
    scope: str,
    target: str,
    trigger: str,
    hours: float,
) -> MeteoraCooldown:
    """Insert or extend a cooldown; repeated triggers accumulate event_count."""
    now = datetime.now(UTC)
    expires = now + timedelta(hours=hours)
    existing = (
        session.query(MeteoraCooldown)
        .filter(
            MeteoraCooldown.scope == scope,
            MeteoraCooldown.target == target,
            MeteoraCooldown.trigger == trigger,
        )
        .first()
    )
    if existing:
        existing.event_count += 1
        existing.expires_at = max(existing.expires_at, expires) if existing.expires_at else expires
        row = existing
    else:
        row = MeteoraCooldown(
            scope=scope,
            target=target,
            trigger=trigger,
            event_count=1,
            expires_at=expires,
            created_at=now,
        )
        session.add(row)
    session.commit()
    logger.debug(f"meteora cooldown {scope}:{target} ({trigger}) until {expires}")
    return row
