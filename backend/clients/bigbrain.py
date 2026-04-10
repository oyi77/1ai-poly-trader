"""BigBrain client for PolyEdge - unified memory across all apps."""

import httpx
import os
from dataclasses import dataclass
from typing import Optional, List

BRAIN_BASE_URL = "http://localhost:9099"  # berkahkarya-hub API


@dataclass
class BrainMemory:
    id: str
    content: str
    wing: str  # "trading", "strategy", "weather", etc.
    room: str  # subcategory
    source: str = "polyedge"


class BigBrain:
    """
    Unified brain client for PolyEdge.
    Reads from and writes to MemPalace via berkahkarya-hub API.
    """

    def __init__(self, base_url: str = None, timeout: float = 10.0):
        self.base_url = base_url or (os.environ.get("BRAIN_API_URL") or BRAIN_BASE_URL)
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def search(
        self, query: str, wing: Optional[str] = None, limit: int = 10
    ) -> List[BrainMemory]:
        """Search brain for relevant memories."""
        client = await self._get_client()
        params = {"query": query}
        if wing:
            params["wing"] = wing
        if limit is not None:
            params["limit"] = str(limit)
        try:
            resp = await client.get(f"{self.base_url}/brain/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            memories: List[BrainMemory] = []
            items = data if isinstance(data, list) else data.get("memories", [])
            for item in items:
                memories.append(
                    BrainMemory(
                        id=str(
                            item.get("id")
                            or item.get("memory_id")
                            or item.get("memoryId")
                            or item.get("memory", "")
                        ),
                        content=str(item.get("content", "")),
                        wing=str(item.get("wing", wing or "")),
                        room=str(item.get("room", "")),
                        source=str(item.get("source", "polyedge")),
                    )
                )
            return memories
        except Exception:
            # Gracefully degrade if brain service is unavailable
            return []

    async def _write_memory(self, wing: str, room: str, content: str) -> Optional[str]:
        client = await self._get_client()
        payload = {"wing": wing, "room": room, "content": content}
        try:
            resp = await client.post(f"{self.base_url}/brain/add", json=payload)
            resp.raise_for_status()
            data = resp.json()
            mem_id = None
            if isinstance(data, dict):
                mem_id = data.get("memoryId") or data.get("id") or data.get("memory_id")
            return mem_id
        except Exception:
            return None

    async def write_trade_outcome(self, trade_data: dict) -> Optional[str]:
        """
        Write a trade outcome to brain memory.
        trade_data contains: strategy, market, direction, pnl, edge, confidence, timestamp
        """
        direction = trade_data.get("direction", "")
        market = trade_data.get("market", trade_data.get("market_ticker", "unknown"))
        result = trade_data.get("result", "")
        pnl = trade_data.get("pnl")
        edge = trade_data.get("edge")
        strategy = trade_data.get("strategy", "")
        timestamp = trade_data.get("timestamp")
        content = f"Trade {direction} {market} {result} PnL:{pnl} edge:{edge} strategy:{strategy}"
        room = "outcomes"
        wing = "trading"
        if timestamp:
            content = f"[{timestamp}] {content}"
        return await self._write_memory(wing=wing, room=room, content=content)

    async def write_strategy_insight(
        self, strategy: str, insight: str, confidence: float
    ) -> Optional[str]:
        content = (
            f"Strategy insight: {strategy} - {insight} (confidence={confidence:.3f})"
        )
        return await self._write_memory(
            wing="trading", room="insights", content=content
        )

    async def get_trading_history(
        self, strategy: str = None, limit: int = 100
    ) -> List[dict]:
        query = ""
        if strategy:
            query = f"strategy:{strategy}"
        memories = await self.search(query=query, wing="trading", limit=limit)
        return [
            {
                "id": m.id,
                "content": m.content,
                "wing": m.wing,
                "room": m.room,
                "source": m.source,
            }
            for m in memories
        ]

    async def get_best_strategies(self) -> List[dict]:
        # Simple heuristic: fetch insights and return as a list for later ranking
        memories = await self.search(
            query="room:insights OR content:insight", wing="trading", limit=50
        )
        results = []
        for m in memories:
            results.append(
                {
                    "id": m.id,
                    "content": m.content,
                    "wing": m.wing,
                    "room": m.room,
                    "source": m.source,
                }
            )
        return results

    async def write_calibration_update(
        self, city: str, forecast: float, actual: float, error: float
    ):
        content = f"Calibration update: city={city} forecast={forecast} actual={actual} error={error}"
        return await self._write_memory(
            wing="weather", room="calibration", content=content
        )


_bigbrain_instance: Optional[BigBrain] = None


def get_bigbrain() -> BigBrain:
    global _bigbrain_instance
    if _bigbrain_instance is None:
        _bigbrain_instance = BigBrain()
    return _bigbrain_instance


async def close_bigbrain():
    global _bigbrain_instance
    if _bigbrain_instance is not None:
        await (
            _bigbrain_instance._client.aclose()
        ) if _bigbrain_instance._client else None
        _bigbrain_instance = None
