"""Live smoke tests for Meteora APIs.

Skipped unless METEORA_LIVE=1 (network-dependent, rate-limited):

    METEORA_LIVE=1 pytest backend/tests/test_meteora_live_smoke.py
"""
import os

import pytest

from backend.data.meteora.client import (
    MeteoraDLMMClient,
    MeteoraDiscoveryClient,
)

SOL_USDC = "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("METEORA_LIVE") != "1",
        reason="live-network smoke; set METEORA_LIVE=1 to run",
    ),
]


async def test_live_discovery_returns_scorer_fields():
    pools = await MeteoraDiscoveryClient().fetch_pools(page_size=5, timeframe="30m")
    assert isinstance(pools, list) and pools, "discovery returned no pools"
    sample = pools[0]
    assert {"pool_address", "active_tvl", "fee_active_tvl_ratio"} <= set(sample)


async def test_live_ohlcv_and_volume_history():
    dlmm = MeteoraDLMMClient()
    candles = await dlmm.get_ohlcv(SOL_USDC, timeframe="24h")
    buckets = await dlmm.get_volume_history(SOL_USDC, timeframe="24h")
    assert isinstance(candles, list)
    assert isinstance(buckets, list)
    if buckets:
        assert {"volume", "fees"} <= set(buckets[0])
