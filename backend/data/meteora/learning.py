"""Darwinian learning loop: signal-weight evolution + lesson derivation.

Ported from meridian signal-weights.js / lessons.js semantics: weights are
boosted or decayed per closed-position win-rate correlation, clamped to
[FLOOR, CEILING]; lessons persist for notably good/bad closes.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from backend.data.meteora.screening import SIGNAL_NAMES

BOOST = 1.05
DECAY = 0.95
FLOOR = 0.3
CEILING = 2.5
RECALC_EVERY = 5
WINDOW_DAYS = 60
MAX_LESSON_LEN = 400
LESSON_PNL_THRESHOLD_PCT = 2.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sanitize_lesson_text(text: str, max_len: int = MAX_LESSON_LEN) -> str:
    cleaned = " ".join(str(text).replace(chr(13), " ").replace(chr(10), " ").split())
    return "".join(ch for ch in cleaned if ch not in "<>`")[:max_len]


def performance_snapshot(pos) -> dict[str, Any]:
    snap = dict(pos.signal_snapshot or {})
    snap.update(
        {
            "position_id": pos.id,
            "pool_address": pos.pool_address,
            "pool_name": pos.pool_name,
            "strategy": pos.strategy,
            "side": pos.side,
            "bin_step": pos.bin_step,
            "pnl_pct": pos.pnl_pct,
            "fees_usd": pos.fees_earned_usd,
            "minutes_held": pos.minutes_held,
            "minutes_in_range": pos.minutes_in_range,
            "oor_events": pos.oor_event_count,
            "close_reason": pos.close_reason,
            "amount_sol": pos.amount_sol,
        }
    )
    return {k: v for k, v in snap.items() if v is not None}


def derive_lesson(session, pos):
    """Persist a lesson for a notably good/bad close; returns row or None."""
    from backend.models.meteora_db import MeteoraLesson

    if pos.pnl_pct is None:
        return None
    if abs(pos.pnl_pct) < LESSON_PNL_THRESHOLD_PCT:
        return None

    kind = "positive" if pos.pnl_pct > 0 else "negative"
    reason = pos.close_reason or "unknown"
    if kind == "negative":
        text = (
            f"{pos.pool_name} {pos.strategy}/{pos.side} closed "
            f"{pos.pnl_pct:.1f}% via {reason}. Avoid similar entries: review "
            f"signal snapshot and regime before redeploying here."
        )
    else:
        text = (
            f"{pos.pool_name} {pos.strategy}/{pos.side} printed "
            f"{pos.pnl_pct:.1f}% via {reason}. Pattern worth repeating."
        )
    row = MeteoraLesson(
        position_id=pos.id,
        pool_address=pos.pool_address,
        kind=kind,
        text=sanitize_lesson_text(text),
        perf_snapshot=performance_snapshot(pos),
        created_at=datetime.now(UTC),
    )
    session.add(row)
    logger.debug(f"[meteora-learning] lesson ({kind}) for #{pos.id}")
    return row


def _closed_positions(session, window_days: int):
    from backend.models.meteora_db import MeteoraPosition

    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    return (
        session.query(MeteoraPosition)
        .filter(
            MeteoraPosition.mode == "paper",
            MeteoraPosition.status == "closed",
            MeteoraPosition.closed_at.isnot(None),
            MeteoraPosition.closed_at >= cutoff,
        )
        .all()
    )


def recalc_signal_weights(
    session,
    *,
    window_days: int = WINDOW_DAYS,
    boost: float = BOOST,
    decay: float = DECAY,
    floor: float = FLOOR,
    ceiling: float = CEILING,
) -> dict[str, float]:
    """Presence-based win-rate correlation per signal; clamped evolution."""
    from backend.models.meteora_db import MeteoraSignalWeight

    positions = _closed_positions(session, window_days)
    existing = {w.signal_name: w for w in session.query(MeteoraSignalWeight).all()}
    new_weights: dict[str, float] = {}

    for name in SIGNAL_NAMES:
        row = existing.get(name)
        current = row.weight if row else 1.0
        present_win = present_loss = absent_win = absent_loss = 0
        for p in positions:
            if p.pnl_pct is None:
                continue
            present = (p.signal_snapshot or {}).get(name) is not None
            won = p.pnl_pct > 0
            if present and won:
                present_win += 1
            elif present:
                present_loss += 1
            elif won:
                absent_win += 1
            else:
                absent_loss += 1

        n_present = present_win + present_loss
        n_absent = absent_win + absent_loss
        samples = n_present + n_absent
        if samples == 0:
            new_weights[name] = current
            continue

        wr_with = present_win / n_present if n_present else 0.0
        wr_without = absent_win / n_absent if n_absent else 0.0
        if n_present and n_absent:
            factor = boost if wr_with >= wr_without else decay
        else:
            factor = 1.0
        candidate = _clamp(current * factor, floor, ceiling)

        if row is None:
            row = MeteoraSignalWeight(signal_name=name)
            session.add(row)
        row.weight = candidate
        row.sample_count = samples
        row.win_rate_with_signal = round(wr_with, 4)
        row.win_rate_without_signal = round(wr_without, 4)
        row.last_recalc_at = datetime.now(UTC)
        new_weights[name] = candidate

    session.commit()
    logger.info(f"[meteora-learning] weights recalculated over {len(positions)} closes")
    return new_weights


def should_recalc(session, *, every: int = RECALC_EVERY) -> bool:
    count = len(_closed_positions(session, window_days=WINDOW_DAYS))
    return count > 0 and count % every == 0


def recent_lessons(session, limit: int = 20):
    from backend.models.meteora_db import MeteoraLesson

    return (
        session.query(MeteoraLesson)
        .order_by(MeteoraLesson.created_at.desc())
        .limit(limit)
        .all()
    )
