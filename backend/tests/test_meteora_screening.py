"""Screener unit tests — Degen Score port, hard filters, cooldowns.

Pure-function tests use synthetic pools; the fixture smoke replays the
recorded discovery page end-to-end with no network.
"""
import json
from pathlib import Path

import pytest

from backend.data.meteora.screening import (
    DegenTargets,
    ScreeningFilters,
    build_signal_snapshot,
    degen_score,
    passes_hard_filters,
    screen_pools,
)

FIXTURES = Path(__file__).parent / "fixtures" / "meteora"


def make_pool(**overrides):
    """Balanced pool that saturates every Degen sub-score at 30m defaults."""
    pool = {
        "pool_address": "PoolA",
        "name": "TEST-SOL",
        "active_tvl": 100_000.0,
        "volume_active_tvl_ratio": 20.0,   # s_trading = 1.0
        "fee_active_tvl_ratio": 0.20,      # s_fees = 1.0
        "unique_lps": 30.0,
        "positions_created": 10.0,         # s_lp = 40/40 = 1.0
        "volatility": 5.0,
        "base_token_holders": 1200,
        "dlmm_params": {"bin_step": 100},
        "token_x": {
            "address": "MintA",
            "organic_score": 80,
            "market_cap": 500_000,
            "launchpad": "pumpfun",
        },
        "token_y": {"address": "SOL", "organic_score": 95},
        "volume": 400_000,
    }
    pool.update(overrides)
    return pool


# ---------------------------------------------------------------------------
# degen_score


def test_balanced_pool_scores_100():
    score, subs = degen_score(make_pool())
    assert score == pytest.approx(100.0)
    assert all(v == pytest.approx(1.0) for v in subs.values())


def test_zero_active_tvl_scores_zero():
    score, subs = degen_score(make_pool(active_tvl=0))
    assert score == 0.0
    assert set(subs) == {"trading", "lp", "fees", "liquidity"}


def test_single_spiked_metric_cannot_dominate():
    # Three subs perfect, trading tiny → geometric mean punishes imbalance.
    pool = make_pool(volume_active_tvl_ratio=0.2)  # s_trading = 0.01
    score, _ = degen_score(pool)
    expected = (0.01 * 1.0 * 1.0 * 1.0) ** 0.25 * 100
    assert score == pytest.approx(expected)
    assert score < 32.0


def test_timeframe_normalization_keeps_targets_valid():
    """Same underlying rate on a longer window must yield the same score."""
    p30 = make_pool()  # ratios already in 30m terms
    s30, _ = degen_score(p30, timeframe="30m")

    # Same economics observed over a 1h window halves the per-window ratio.
    p60 = make_pool(
        volume_active_tvl_ratio=40.0,
        fee_active_tvl_ratio=0.40,
        unique_lps=60.0,
        positions_created=20.0,
    )
    s60, _ = degen_score(p60, timeframe="1h")
    assert s60 == pytest.approx(s30)


def test_custom_targets_respected():
    targets = DegenTargets(target_vol_ratio=10.0)
    score, subs = degen_score(
        make_pool(volume_active_tvl_ratio=10.0), targets=targets
    )
    assert subs["trading"] == pytest.approx(1.0)
    assert score == pytest.approx(100.0)


def test_log_liquidity_floor_dust_pool():
    # $100 TVL with otherwise perfect ratios → liquidity sub-score ≈ log ratio
    _, subs = degen_score(make_pool(active_tvl=100.0))
    import math

    assert subs["liquidity"] == pytest.approx(math.log10(100) / math.log10(20000))


# ---------------------------------------------------------------------------
# passes_hard_filters


def test_filter_rejects_low_tvl():
    ok, reason = passes_hard_filters(make_pool(active_tvl=1000.0), ScreeningFilters())
    assert not ok and "tvl" in reason


def test_filter_rejects_non_dlmm_pool_type_explicitly():
    pool = make_pool(pool_type="damm_v2", dlmm_params=None)
    ok, reason = passes_hard_filters(pool, ScreeningFilters())
    assert not ok and reason == "pool_type damm_v2 not supported"


def test_filter_accepts_explicit_dlmm_type():
    ok, reason = passes_hard_filters(make_pool(pool_type="dlmm"), ScreeningFilters())
    assert ok and reason is None


def test_filter_rejects_missing_bin_step():
    pool = make_pool()
    del pool["dlmm_params"]
    ok, reason = passes_hard_filters(pool, ScreeningFilters())
    assert not ok and "bin_step" in reason


def test_filter_rejects_bin_step_out_of_range():
    ok, reason = passes_hard_filters(
        make_pool(dlmm_params={"bin_step": 250}), ScreeningFilters()
    )
    assert not ok and "bin_step" in reason


def test_filter_rejects_low_organic_when_present():
    ok, reason = passes_hard_filters(
        make_pool(token_x={"address": "A", "organic_score": 10}), ScreeningFilters()
    )
    assert not ok and "organic" in reason


def test_filter_allows_missing_organic():
    """Upstream organic_score is nullable — absence must not reject."""
    pool = make_pool(
        token_x={"address": "A", "market_cap": 500_000},
        token_y={"address": "SOL"},
    )
    ok, reason = passes_hard_filters(pool, ScreeningFilters())
    assert ok and reason is None


def test_filter_rejects_blocked_launchpad():
    f = ScreeningFilters(blocked_launchpads={"raydium"})
    ok, reason = passes_hard_filters(
        make_pool(
            token_x={"address": "A", "market_cap": 500_000, "launchpad": "raydium"}
        ),
        f,
    )
    assert not ok and "launchpad" in reason


def test_filter_optional_bot_pct_applies_only_when_present():
    ok, _ = passes_hard_filters(make_pool(), ScreeningFilters())  # absent → pass
    assert ok
    pool = make_pool(bot_holders_pct=90)
    ok2, reason2 = passes_hard_filters(pool, ScreeningFilters())
    assert not ok2 and "bot" in reason2


# ---------------------------------------------------------------------------
# screen_pools orchestration


def test_screen_pools_sorts_and_flags():
    good = make_pool(name="GOOD")
    bad = make_pool(pool_address="BadTVL", name="BAD", active_tvl=100.0)
    results = screen_pools([bad, good], filters=ScreeningFilters())
    assert [r.pool_address for r in results] == ["PoolA", "BadTVL"]
    assert not results[0].rejected and results[1].rejected
    assert "tvl" in results[1].reject_reason


def test_screen_pools_cooldown_by_pool_and_mint():
    cool = {("pool", "PoolA"), ("base_mint", "MintB")}
    pools = [
        make_pool(),
        make_pool(pool_address="PoolB", token_x={"address": "MintB"}),
    ]
    results = screen_pools(pools, filters=ScreeningFilters(), cooldown_targets=cool)
    reasons = {r.pool_address: r.reject_reason for r in results}
    assert reasons["PoolA"] == "cooldown active"
    assert reasons["PoolB"] == "cooldown active"


def test_signal_snapshot_carries_weighted_score():
    results = screen_pools(
        [make_pool()],
        filters=ScreeningFilters(),
        signal_weights={"organic_score": 1.25},
    )
    snap = results[0].signal_snapshot
    assert snap["weighted_score"] == pytest.approx(results[0].degen_score * 1.25)


def test_snapshot_includes_quote_organic():
    snap = build_signal_snapshot(make_pool(), "30m")
    assert snap["quote_organic_score"] == 95


# ---------------------------------------------------------------------------
# Fixture smoke — replay the real discovery page


def test_fixture_page_screens_without_error():
    data = json.loads((FIXTURES / "discovery_pools_trending_30m.json").read_text())
    pools = data.get("data") or []
    assert pools, "fixture unexpectedly empty"
    results = screen_pools(pools, filters=ScreeningFilters(), timeframe="30m")
    assert len(results) == len(pools)
    scores = [r.degen_score for r in results]
    assert scores == sorted(scores, reverse=True)
