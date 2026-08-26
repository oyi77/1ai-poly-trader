"""Autoresearch benchmark — deterministic strategy-performance measurement.

Seeds a synthetic, fixed-seed signal history into a throwaway SQLite DB and
runs the production BacktestEngine (backend/core/backtester.py) over it.
Emits METRIC lines for the autoresearch loop. No network, no wall-clock
dependence: identical output on every run (verified in-process by a
double-run equality guard).
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SEED = 42
N_SIGNALS = 1500
STRATEGY = "bench_seed"
WINDOW_START = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW_DAYS = 60


def build_db(db_path: str) -> None:
    """Create schema + seed the deterministic signal history."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import backend.models.database as dbmod  # registers all tables
    from backend.models.engine import Base

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    rng = random.Random(SEED)
    tickers = [f"BTC-UP-5M-{i:03d}" for i in range(40)]
    base_ts = WINDOW_START
    step = timedelta(minutes=WINDOW_DAYS * 24 * 60 / N_SIGNALS)

    rows = []
    for i in range(N_SIGNALS):
        mp = round(rng.uniform(0.55, 0.92), 3)     # model probability
        mv = round(rng.uniform(0.35, 0.65), 3)     # market price
        edge = round(mp - mv, 3)
        direction = "up" if i % 2 == 0 else "down"
        # Edge-informative outcome: stronger edge ⇒ higher win probability.
        p_win = 0.72 if edge > 0.15 else 0.55
        outcome_correct = rng.random() < p_win
        rows.append(
            dict(
                market_ticker=tickers[i % len(tickers)],
                platform="polymarket",
                market_type="btc",
                timestamp=base_ts + step * i,
                direction=direction,
                model_probability=mp,
                market_price=mv,
                edge=edge,
                confidence=round(mp, 3),
                reasoning=f"{STRATEGY} synthetic deterministic signal #{i}",
                outcome_correct=outcome_correct,
                settled_at=base_ts + step * i + timedelta(minutes=5),
            )
        )
    db.execute(dbmod.Signal.__table__.insert(), rows)
    db.commit()
    db.close()
    engine.dispose()


async def run_once(db_path: str) -> dict[str, float]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.core.backtester import BacktestConfig, BacktestEngine

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        cfg = BacktestConfig(
            strategy_name=STRATEGY,
            start_date=WINDOW_START,
            end_date=WINDOW_START + timedelta(days=WINDOW_DAYS),
            initial_bankroll=1000.0,
            min_edge_threshold=0.10,
            min_model_probability=0.65,
            calibration_shrinkage=5.0,
        )
        result = await BacktestEngine(cfg).run(db)
        return {
            "bench_total_pnl": round(float(result.total_pnl), 4),
            "bench_sharpe": round(float(result.sharpe_ratio), 4),
            "bench_win_rate": round(float(result.win_rate), 4),
            "bench_return_pct": round(float(result.return_pct), 4),
            "bench_max_drawdown": round(float(result.max_drawdown), 4),
            "bench_profit_factor": round(float(result.profit_factor), 4),
            "bench_trades": float(result.total_trades),
        }
    finally:
        db.close()
        engine.dispose()


def main() -> int:
    from loguru import logger

    logger.remove()  # keep stdout METRIC-clean

    metrics_a: dict[str, float] = {}
    metrics_b: dict[str, float] = {}

    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "run_a.db")
        b = os.path.join(tmp, "run_b.db")
        build_db(a)
        build_db(b)
        metrics_a = asyncio.run(run_once(a))
        metrics_b = asyncio.run(run_once(b))

    if metrics_a != metrics_b:
        print("NONDETERMINISM DETECTED — double-run metrics diverged:")
        for k in sorted(metrics_a):
            if metrics_a[k] != metrics_b.get(k):
                print(f"  {k}: {metrics_a[k]} != {metrics_b.get(k)}")
        return 2

    for k in sorted(metrics_a):
        print(f"METRIC {k}={metrics_a[k]}")
    print(
        f"BENCH OK seed={SEED} signals={N_SIGNALS} strategy={STRATEGY} "
        f"deterministic=true"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
