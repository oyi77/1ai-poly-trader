"""Meteora API client tests — respx-mocked, zero live network.

Live smoke tests live in test_meteora_live_smoke.py (marked `live`, skipped
by default). This suite replays recorded fixtures from
backend/tests/fixtures/meteora/.
"""
import json
from pathlib import Path

import httpx
import pytest
import respx

from backend.data.meteora.client import (
    JupiterClient,
    MeteoraDiscoveryClient,
    MeteoraDLMMClient,
    _request_json,
    validate_timeframe,
)

FIXTURES = Path(__file__).parent / "fixtures" / "meteora"

DISCOVERY_BASE = "https://pool-discovery-api.datapi.meteora.ag"
DLMM_BASE = "https://dlmm.datapi.meteora.ag"
JUPITER_BASE = "https://datapi.jup.ag/v1"

POOL = "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# validate_timeframe


def test_validate_timeframe_accepts_documented_enum():
    for tf in ("5m", "30m", "1h", "2h", "4h", "12h", "24h"):
        assert validate_timeframe(tf) == tf


def test_validate_timeframe_rejects_unknown():
    with pytest.raises(ValueError, match="timeframe must be one of"):
        validate_timeframe("1day")


# ---------------------------------------------------------------------------
# Discovery client


@respx.mock
async def test_fetch_pools_parses_data_and_params():
    fixture = _load("discovery_pools_trending_30m.json")
    route = respx.get(f"{DISCOVERY_BASE}/pools").respond(json=fixture)
    client = MeteoraDiscoveryClient()
    pools = await client.fetch_pools(page_size=25, timeframe="30m", category="trending")
    assert route.called
    sent = route.calls.last.request.url.params
    assert sent["page_size"] == "25"
    assert sent["timeframe"] == "30m"
    assert sent["category"] == "trending"
    assert isinstance(pools, list) and len(pools) > 0
    # Scorer fields present on discovery rows
    sample = pools[0]
    for field in (
        "pool_address",
        "active_tvl",
        "fee_active_tvl_ratio",
        "volume_active_tvl_ratio",
        "unique_lps",
        "positions_created",
    ):
        assert field in sample, f"missing scorer field {field}"


@respx.mock
async def test_fetch_pools_empty_data_returns_empty_list():
    respx.get(f"{DISCOVERY_BASE}/pools").respond(json={"data": []})
    client = MeteoraDiscoveryClient()
    assert await client.fetch_pools(page_size=10) == []


@respx.mock
async def test_fetch_pool_detail_returns_first_row():
    fixture = _load("discovery_pool_detail.json")
    respx.get(f"{DISCOVERY_BASE}/pools").respond(json=fixture)
    client = MeteoraDiscoveryClient()
    detail = await client.fetch_pool_detail(POOL)
    assert detail is not None
    assert detail.get("pool_address") == POOL


@respx.mock
async def test_fetch_pool_detail_missing_returns_none():
    respx.get(f"{DISCOVERY_BASE}/pools").respond(json={"data": []})
    assert await MeteoraDiscoveryClient().fetch_pool_detail("nosuch") is None


# ---------------------------------------------------------------------------
# DLMM client


@respx.mock
async def test_get_ohlcv_parses_candles():
    fixture = _load("dlmm_ohlcv_24h.json")
    route = respx.get(f"{DLMM_BASE}/pools/{POOL}/ohlcv").respond(json=fixture)
    candles = await MeteoraDLMMClient().get_ohlcv(
        POOL, timeframe="24h", start_time=1755000000, end_time=1756100000
    )
    assert route.called
    params = route.calls.last.request.url.params
    assert params["timeframe"] == "24h"
    assert params["start_time"] == "1755000000"
    assert candles and {"timestamp", "open", "high", "low", "close"} <= set(candles[0])


@respx.mock
async def test_get_volume_history_includes_fees():
    fixture = _load("dlmm_volume_history_24h.json")
    respx.get(f"{DLMM_BASE}/pools/{POOL}/volume/history").respond(json=fixture)
    buckets = await MeteoraDLMMClient().get_volume_history(
        POOL, timeframe="24h", start_time=1755000000, end_time=1756100000
    )
    assert buckets and {"volume", "fees", "protocol_fees"} <= set(buckets[0])


@respx.mock
async def test_get_pool_registry_row():
    fixture = _load("dlmm_pool_detail.json")
    respx.get(f"{DLMM_BASE}/pools/{POOL}").respond(json=fixture)
    pool = await MeteoraDLMMClient().get_pool(POOL)
    assert pool is not None and pool.get("address") == POOL


# ---------------------------------------------------------------------------
# Retry / backoff behavior


@respx.mock
async def test_request_retries_on_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _noop_sleep)
    route = respx.get(f"{DLMM_BASE}/pools/{POOL}").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"address": POOL}),
        ]
    )
    data = await _request_json(f"{DLMM_BASE}/pools/{POOL}")
    assert data == {"address": POOL}
    assert route.call_count == 2


@respx.mock
async def test_request_raises_after_exhausted_retries(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _noop_sleep)
    respx.get(f"{DLMM_BASE}/pools/{POOL}").mock(
        side_effect=[httpx.Response(503)] * 3
    )
    with pytest.raises(httpx.HTTPStatusError):
        await _request_json(f"{DLMM_BASE}/pools/{POOL}")


@respx.mock
async def test_request_honors_retry_after_header(monkeypatch):
    sleeps: list[float] = []

    async def _capture_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("asyncio.sleep", _capture_sleep)
    respx.get(f"{DLMM_BASE}/pools/{POOL}").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={}),
        ]
    )
    await _request_json(f"{DLMM_BASE}/pools/{POOL}")
    assert sleeps == [2.0]


async def _noop_sleep(_delay):
    return None


# ---------------------------------------------------------------------------
# Jupiter client


@respx.mock
async def test_jupiter_search_assets():
    respx.get(f"{JUPITER_BASE}/assets/search").respond(
        json=[{"id": "so11111111111111111111111111111111111111112", "symbol": "SOL"}]
    )
    results = await JupiterClient().search_assets("SOL")
    assert results and results[0]["symbol"] == "SOL"


@respx.mock
async def test_iter_all_pools_follows_cursor_until_exhausted():
    page1 = {"data": [{"pool_address": "a"}], "has_more": True,
             "after_key": "cursor-1"}
    page2 = {"data": [{"pool_address": "b"}], "has_more": True,
             "after_key": "cursor-2"}
    page3 = {"data": [{"pool_address": "c"}], "has_more": False,
             "after_key": None}
    route = respx.get(f"{DISCOVERY_BASE}/pools").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
            httpx.Response(200, json=page3),
        ]
    )
    client = MeteoraDiscoveryClient()
    pages = [pg async for pg in client.iter_all_pools(page_size=1)]
    assert [[r["pool_address"] for r in pg] for pg in pages] == [["a"], ["b"], ["c"]]
    # Cursor param must round-trip on follow-up requests.
    sent_params = [httpx.QueryParams(c.request.url.params).get("after_key")
                   for c in route.calls][1:]
    assert sent_params == ["cursor-1", "cursor-2"]


@respx.mock
async def test_iter_all_pools_respects_max_pages():
    def ok(request):
        return httpx.Response(
            200,
            json={"data": [{"x": 1}], "has_more": True, "after_key": f"k{request.url.params.get('after_key', '')}"},
        )

    respx.get(f"{DISCOVERY_BASE}/pools").mock(side_effect=ok)
    pages = [
        pg
        async for pg in MeteoraDiscoveryClient().iter_all_pools(max_pages=2)
    ]
    assert len(pages) == 2
