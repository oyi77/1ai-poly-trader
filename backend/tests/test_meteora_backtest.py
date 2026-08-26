"""Backtester tests on synthetic paths with known outcomes.

Model: terminal composition is path-independent v3/DLMM math calibrated so
the seeded structure valued at entry reproduces its deployed capital
(one-sided shapes hold the complement as idle quote cash). Consequences:
- Zero-invariant: any path ending at entry returns the capital.
- Path independence: shared exit price ⇒ shared terminal value (and any
  exit beyond a range edge is one identical all-quote state).
- Realized IL: exiting above the range locks in < deposit vs quote-HODL.
- Non-reverting dips leave every touched bin ≤ par ⇒ final < deposit.
Fees accrue pro-rata while in range, reported separately.
"""
import math

import pytest

from backend.data.meteora.backtest import (
    ShapeConfig,
    default_shape_grid,
    rank_shapes,
    simulate,
    walk_forward,
)

BUCKET_SEC = 300


def _fees(n, per_bucket):
    return [per_bucket] * n


def _v_path(p0, step_pct, depth):
    """Down `depth` multiplicative steps then back up to exactly p0."""
    descent = [p0 * (1 - step_pct) ** i for i in range(depth + 1)]
    ascent = list(reversed(descent[:-1]))  # ends at p0
    return descent + ascent


def _run(closes, shape, *, fees=0.0, tvl=1e9, capital=100.0):
    return simulate(
        closes=closes,
        highs=[c * 1.001 for c in closes],
        lows=[c * 0.999 for c in closes],
        bucket_fees=_fees(len(closes), fees),
        bucket_seconds=BUCKET_SEC,
        active_tvl=tvl,
        shape=shape,
        capital=capital,
    )


def test_round_trip_zero_fees_nets_zero_two_sided():
    p0 = 100.0
    closes = _v_path(p0, 0.01, 5)
    assert closes[-1] == p0
    r = _run(closes, ShapeConfig("spot", "two_sided", 20, 20))
    assert r.net_pnl_usd == pytest.approx(0.0, abs=1e-9)
    assert r.final_value_usd == pytest.approx(r.capital, rel=1e-9)


def test_round_trip_zero_fees_nets_zero_bid_ladder():
    p0 = 200.0
    closes = _v_path(p0, 0.008, 14)
    assert closes[-1] == p0
    r = _run(closes, ShapeConfig("bid_ask", "bid", 69, 69))
    assert r.net_pnl_usd == pytest.approx(0.0, abs=1e-9)


def test_fees_make_round_trip_profitable():
    p0 = 100.0
    closes = _v_path(p0, 0.01, 5)
    capital, tvl = 10_000.0, 100_000.0
    r = _run(
        closes,
        ShapeConfig("spot", "two_sided", 20, 20),
        fees=50.0,
        tvl=tvl,
        capital=capital,
    )
    share = min(1.0, capital / tvl)
    assert r.fees_usd > 0
    assert r.net_pnl_usd > 0
    assert r.fees_usd == pytest.approx(50.0 * (len(closes) - 1) * share)


def test_any_exit_above_range_yields_identical_value():
    """Beyond the top bin the position is pure quote — exit level irrelevant."""
    shape = ShapeConfig("spot", "two_sided", 30, 30)

    def rally(mult):
        closes = [100.0 * math.pow(mult, i) for i in range(40)]
        return _run(closes, shape, fees=10.0, tvl=1e7, capital=1_000.0)

    a = rally(1.02)  # +119%
    b = rally(1.05)  # +526%
    assert a.ended_oor and b.ended_oor
    assert a.final_value_usd == pytest.approx(b.final_value_usd, rel=1e-9)
    assert a.hodl_value_usd > a.capital
    assert a.fees_usd > 0

    # Realized IL sign depends on entry position within the range; the
    # physics-guaranteed properties are constancy across exit levels,
    # HODL domination on a rally, and positive fee accrual.
    assert a.hodl_value_usd > a.capital
    assert a.fees_usd > 0
    for r in (a, b):
        assert r.il_usd == pytest.approx(
            r.final_value_usd - r.hodl_value_usd, rel=1e-9
        )

def test_deep_dip_without_recovery_never_exceeds_deposit():
    n = 30
    closes = [100.0 * math.pow(0.985, i) for i in range(n)]  # ~-36%
    r = _run(
        closes,
        ShapeConfig("bid_ask", "bid", 69, 69),
        fees=5.0,
        tvl=1e6,
        capital=1_000.0,
    )
    # Every touched bin converts at par-or-discount on a non-reverting dip.
    assert r.final_value_usd < r.capital
    assert r.pnl_pct < 0
    assert r.minutes_in_range > 0
    assert r.ended_oor is False


def test_path_independence_same_exit_same_value():
    """Terminal value depends only on exit price, never on the route."""
    p0, end = 100.0, 97.0
    v_path = _v_path(p0, 0.01, 5)[:-1] + [end]
    straight = [p0 + (end - p0) * i / 9 for i in range(10)]
    shape = ShapeConfig("spot", "two_sided", 20, 20)
    a = _run(v_path, shape)
    b = _run(straight, shape)
    assert a.final_value_usd == pytest.approx(b.final_value_usd, rel=1e-9)


def test_curve_concentrates_more_than_spot_near_center():
    """Identical center-hugging oscillation: curve never meaningfully worse."""
    p0 = 100.0
    closes = [p0 * 1.01 if i % 2 else p0 for i in range(60)]
    spot = _run(
        closes,
        ShapeConfig("spot", "two_sided", 20, 20),
        fees=100.0,
        tvl=1e6,
        capital=10_000.0,
    )
    curve = _run(
        closes,
        ShapeConfig("curve", "two_sided", 20, 20),
        fees=100.0,
        tvl=1e6,
        capital=10_000.0,
    )
    assert curve.fees_usd >= spot.fees_usd * 0.99


def test_input_validation():
    with pytest.raises(ValueError):
        ShapeConfig("nope")
    with pytest.raises(ValueError):
        ShapeConfig("spot", "sideways")
    with pytest.raises(ValueError):
        ShapeConfig("spot", "two_sided", 0, 10)
    with pytest.raises(ValueError, match="length mismatch"):
        simulate(
            closes=[1, 2],
            highs=[1],
            lows=[1],
            bucket_fees=[],
            bucket_seconds=60,
            active_tvl=1.0,
        )


def test_rank_shapes_orders_by_pnl_desc():
    n = 25
    closes = [100.0 + i for i in range(n)]  # steady grind up
    ranked = rank_shapes(
        closes=closes,
        highs=[c + 0.5 for c in closes],
        lows=[c - 0.5 for c in closes],
        bucket_fees=_fees(n, 20.0),
        bucket_seconds=BUCKET_SEC,
        active_tvl=500_000.0,
        shapes=default_shape_grid(),
    )
    pnls = [r.pnl_pct for r in ranked]
    assert pnls == sorted(pnls, reverse=True)
    assert len(ranked) == len(default_shape_grid())


def test_walk_forward_reports_both_windows():
    n = 60
    closes = [100.0 + (i if i < 40 else -i * 0.5) for i in range(n)]
    report = walk_forward(
        closes=closes,
        highs=[c + 0.4 for c in closes],
        lows=[c - 0.4 for c in closes],
        bucket_fees=_fees(n, 30.0),
        bucket_seconds=BUCKET_SEC,
        active_tvl=250_000.0,
    )
    assert len(report) == len(default_shape_grid())
    for stats in report.values():
        assert {"train_pnl_pct", "test_pnl_pct", "delta"} <= set(stats)
