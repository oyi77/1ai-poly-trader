"""Meteora DLMM async API clients.

Three hosts, one shared HTTP stack:

- Discovery API  (pool-discovery-api.datapi.meteora.ag) — screening fields:
  active_tvl, fee_active_tvl_ratio, volume_active_tvl_ratio, unique_lps,
  positions_created, volatility, organic_score, base_token_holders,
  dlmm_params.bin_step, launchpad/mcap on token_x/token_y.
- DLMM API       (dlmm.datapi.meteora.ag) — /pools registry, per-pool OHLCV,
  volume/fee history buckets, position event history.
- Jupiter datapi (datapi.jup.ag/v1) — token audits/search fallback.

Rate limiting: single-process sliding window capped under the documented
30 RPS API limit (settings.RATE_LIMIT_METEORA). Retries: exponential backoff
on 429/5xx/network errors, honoring Retry-After when present.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from loguru import logger

from backend.config import settings

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
MAX_RETRIES = 3
BACKOFF_BASE = settings.RATE_LIMIT_BACKOFF_BASE


class _RateLimiter:
    """Sliding-window limiter shared by all Meteora/Jupiter clients."""

    def __init__(self, max_per_second: float) -> None:
        self._max = float(max_per_second)
        self._events: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._events = [t for t in self._events if now - t < 1.0]
            if len(self._events) >= self._max:
                wait = 1.0 - (now - self._events[0])
                if wait > 0:
                    await asyncio.sleep(wait)
            self._events.append(time.monotonic())


_limiter = _RateLimiter(max_per_second=settings.RATE_LIMIT_METEORA)
_shared_client: httpx.AsyncClient | None = None


def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
    return _shared_client


async def close_shared_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None


async def _request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """GET JSON with rate limiting + bounded exponential-backoff retries."""
    http = client or get_shared_client()
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        await _limiter.acquire()
        try:
            resp = await http.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else BACKOFF_BASE**attempt
                )
                logger.warning(
                    f"meteora client {resp.status_code} on {url} — retry "
                    f"{attempt + 1}/{MAX_RETRIES} in {delay:.1f}s"
                )
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.TransportError, httpx.HTTPError) as exc:
            last_exc = exc
            delay = BACKOFF_BASE**attempt
            logger.warning(
                f"meteora client error on {url}: {exc} — retry "
                f"{attempt + 1}/{MAX_RETRIES} in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


VALID_TIMEFRAMES = ("5m", "30m", "1h", "2h", "4h", "12h", "24h")


def validate_timeframe(timeframe: str) -> str:
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {VALID_TIMEFRAMES}, got {timeframe!r}")
    return timeframe


class MeteoraDiscoveryClient:
    """Pool discovery + screening fields (the Degen-score inputs)."""

    base_url = settings.METEORA_DISCOVERY_API_URL

    async def fetch_pools(
        self,
        *,
        page_size: int = 100,
        filter_by: str | None = None,
        timeframe: str = "30m",
        category: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        validate_timeframe(timeframe)
        params: dict[str, Any] = {"page_size": page_size, "timeframe": timeframe}
        if filter_by:
            params["filter_by"] = filter_by
        if category:
            params["category"] = category
        data = await _request_json(f"{self.base_url}/pools", params=params, client=client)
        pools = data.get("data") if isinstance(data, dict) else data
        return pools or []

    async def iter_all_pools(
        self,
        *,
        page_size: int = 100,
        filter_by: str | None = None,
        timeframe: str = "30m",
        category: str | None = None,
        max_pages: int = 50,
        client=None,
    ):
        """Cursor-paginated pool iterator (after_key + has_more envelope).

        Yields lists of pool dicts per page, at most `max_pages` pages.
        """
        validate_timeframe(timeframe)
        after_key: str | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "page_size": page_size,
                "timeframe": timeframe,
            }
            if filter_by:
                params["filter_by"] = filter_by
            if category:
                params["category"] = category
            if after_key:
                params["after_key"] = after_key
            data = await _request_json(
                f"{self.base_url}/pools", params=params, client=client
            )
            rows = data.get("data") or [] if isinstance(data, dict) else []
            if not rows:
                return
            yield rows
            if not (isinstance(data, dict) and data.get("has_more")):
                return
            after_key = data.get("after_key")
            if not after_key:
                return

    async def fetch_pool_detail(
        self,
        pool_address: str,
        *,
        timeframe: str = "30m",
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any] | None:
        validate_timeframe(timeframe)
        data = await _request_json(
            f"{self.base_url}/pools",
            params={
                "page_size": 1,
                "filter_by": f"pool_address={pool_address}",
                "timeframe": timeframe,
            },
            client=client,
        )
        rows = data.get("data") if isinstance(data, dict) else data
        return rows[0] if rows else None


class MeteoraDLMMClient:
    """Pool registry, OHLCV candles, volume/fee history, position events."""

    base_url = settings.METEORA_DLMM_API_URL

    async def get_ohlcv(
        self,
        pool_address: str,
        *,
        timeframe: str = "24h",
        start_time: int | None = None,
        end_time: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        validate_timeframe(timeframe)
        params: dict[str, Any] = {"timeframe": timeframe}
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        data = await _request_json(
            f"{self.base_url}/pools/{pool_address}/ohlcv",
            params=params,
            client=client,
        )
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_volume_history(
        self,
        pool_address: str,
        *,
        timeframe: str = "24h",
        start_time: int | None = None,
        end_time: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        """Buckets: {timestamp, volume, fees, protocol_fees}."""
        validate_timeframe(timeframe)
        params: dict[str, Any] = {"timeframe": timeframe}
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        data = await _request_json(
            f"{self.base_url}/pools/{pool_address}/volume/history",
            params=params,
            client=client,
        )
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_pool(
        self, pool_address: str, *, client: httpx.AsyncClient | None = None
    ) -> dict[str, Any] | None:
        data = await _request_json(f"{self.base_url}/pools/{pool_address}", client=client)
        return data if isinstance(data, dict) else None

    async def get_pools(
        self,
        *,
        limit: int = 100,
        page: int = 1,
        query: str | None = None,
        sort_by: str | None = None,
        filter_by: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "page": page}
        if query:
            params["query"] = query
        if sort_by:
            params["sort_by"] = sort_by
        if filter_by:
            params["filter_by"] = filter_by
        data = await _request_json(f"{self.base_url}/pools", params=params, client=client)
        return data.get("data", []) if isinstance(data, dict) else []


class JupiterClient:
    """Token audit/search via Jupiter DataAPI."""

    base_url = settings.JUPITER_DATAPI_URL

    async def search_assets(
        self, query: str, *, client: httpx.AsyncClient | None = None
    ) -> list[dict[str, Any]]:
        data = await _request_json(
            f"{self.base_url}/assets/search",
            params={"query": query},
            client=client,
        )
        return data if isinstance(data, list) else []


# Module-level singletons -----------------------------------------------------

_discovery: MeteoraDiscoveryClient | None = None
_dlmm: MeteoraDLMMClient | None = None
_jupiter: JupiterClient | None = None


def get_discovery_client() -> MeteoraDiscoveryClient:
    global _discovery
    if _discovery is None:
        _discovery = MeteoraDiscoveryClient()
    return _discovery


def get_dlmm_client() -> MeteoraDLMMClient:
    global _dlmm
    if _dlmm is None:
        _dlmm = MeteoraDLMMClient()
    return _dlmm


def get_jupiter_client() -> JupiterClient:
    global _jupiter
    if _jupiter is None:
        _jupiter = JupiterClient()
    return _jupiter
