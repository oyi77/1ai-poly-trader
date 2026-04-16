"""
WebSocket connection manager for market and whale streams.

This module extracts WebSocket connection management from main.py.
It handles three distinct WebSocket systems:
- /ws/markets: Live market price updates
- /ws/whales: Whale trade notifications
- /ws/events: General event streaming (handled by event_bus)

The three systems are kept separate (per consensus review decision) as they
serve different purposes with different protocols and lifecycles.
"""

import asyncio
import logging
from typing import List, Callable

from fastapi import WebSocket, WebSocketDisconnect


logger = logging.getLogger(__name__)


class WebSocketManager:
    """Base WebSocket connection manager for tracking clients."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, payload: dict):
        """Send a payload to all connected clients."""
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.disconnect(d)


class ChannelWebSocketManager(WebSocketManager):
    """WebSocket manager with channel-specific broadcast support."""

    def __init__(self, channel_name: str):
        super().__init__()
        self.channel_name = channel_name

    async def connect(self, websocket: WebSocket):
        """Connect a client and send welcome message."""
        await super().connect(websocket)
        try:
            await websocket.send_json(
                {"type": "connected", "channel": self.channel_name}
            )
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")


# WebSocket managers for different channels
market_ws = ChannelWebSocketManager("markets")
whale_ws = ChannelWebSocketManager("whales")
stats_ws = ChannelWebSocketManager("stats")


async def broadcast_market_tick(payload: dict) -> None:
    """Broadcast a market tick to all market WebSocket clients."""
    await market_ws.broadcast(payload)


async def broadcast_whale_tick(payload: dict) -> None:
    """Broadcast a whale tick to all whale WebSocket clients."""
    await whale_ws.broadcast(payload)


async def broadcast_stats_update(payload: dict) -> None:
    """Broadcast stats update to all stats WebSocket clients."""
    await stats_ws.broadcast(payload)


# Legacy SSE broadcaster (kept for backward compatibility)
# This handles the ConnectionManager for SSE events
class ConnectionManager:
    """Connection manager for SSE (Server-Sent Events)."""

    def __init__(self):
        self.active_connections: List[asyncio.Queue] = []

    async def connect(self, websocket: WebSocket):
        """Accept and track a new SSE connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove an SSE connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        """Send a message to all connected SSE clients."""
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.debug(f"WebSocket broadcast error (dead connection): {e}")
                # Connection is dead, will be cleaned up on next disconnect
