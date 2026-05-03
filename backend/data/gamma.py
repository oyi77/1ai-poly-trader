"""
Gamma API client for Polymarket market data.

Provides fetch_markets() used by realtime_scanner and other strategies
to retrieve active markets from the Polymarket Gamma API.
"""

import logging
from typing import Any

import httpx

from backend.config import settings

logger = logging.getLogger("trading_bot")

GAMMA_API_URL = f"{settings.GAMMA_API_URL}/markets"


async def fetch_markets(
    limit: int = 100,
    active: bool = True,
    order: str = "volume",
    ascending: bool = False,
) -> list[dict[str, Any]]:
    """Fetch markets from the Polymarket Gamma API.

    Args:
        limit: Maximum number of markets to return.
        active: True for active markets, False for closed/resolved.
        order: Sort field (e.g. 'volume', 'liquidity', 'created').
        ascending: Sort direction.

    Returns:
        List of market dicts from the Gamma API, or empty list on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                GAMMA_API_URL,
                params={
                    "active": str(active).lower(),
                    "closed": str(not active).lower(),
                    "limit": limit,
                    "order": order,
                    "ascending": str(ascending).lower(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            logger.warning(f"[gamma] Unexpected response format: {type(data)}")
            return []
    except httpx.TimeoutException:
        logger.warning("[gamma] Gamma API request timed out")
        return []
    except httpx.HTTPStatusError as e:
        logger.warning(f"[gamma] Gamma API HTTP error: {e.response.status_code}")
        return []
    except Exception as e:
        logger.warning(f"[gamma] Gamma API fetch failed: {e}")
        return []
