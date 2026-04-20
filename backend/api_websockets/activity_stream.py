"""WebSocket activity streaming for real-time strategy decision updates.

Broadcasts activity log entries to all connected WebSocket clients when new
activities are logged via POST /api/activities.
"""

import logging
import asyncio
from typing import Set, Dict, Any
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ActivityConnectionManager:
    """Manages WebSocket connections for activity streaming."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"Activity WebSocket connected. Total clients: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"Activity WebSocket disconnected. Total clients: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: JSON-serializable dictionary to broadcast
        
        Note:
            - Non-blocking: uses asyncio.create_task for each send
            - Automatically removes stale connections on send failure
        """
        if not self.active_connections:
            logger.debug("No active connections to broadcast to")
            return
        
        logger.debug(f"Broadcasting activity to {len(self.active_connections)} clients")
        
        # Create a copy to avoid modification during iteration
        connections = list(self.active_connections)
        
        # Broadcast to all clients concurrently
        tasks = []
        for connection in connections:
            task = asyncio.create_task(self._send_to_client(connection, message))
            tasks.append(task)
        
        # Wait for all sends to complete (with timeout)
        if tasks:
            await asyncio.wait(tasks, timeout=1.0)
    
    async def _send_to_client(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to a single client, handling errors gracefully."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            # Remove stale connection
            await self.disconnect(websocket)


# Global connection manager instance
activity_manager = ActivityConnectionManager()


async def broadcast_activity(activity_data: Dict[str, Any]):
    """
    Broadcast a new activity to all connected WebSocket clients.
    
    Args:
        activity_data: Activity log entry with keys:
            - strategy_name: str
            - decision_type: str
            - confidence_score: float
            - timestamp: str (ISO format)
            - mode: str ('paper', 'testnet', 'live')
            - data: dict (optional additional context)
    
    This function is non-blocking and safe to call from POST handlers.
    """
    # Add message type and timestamp if not present
    message = {
        "type": "activity_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **activity_data
    }
    
    # Create task to avoid blocking caller
    asyncio.create_task(activity_manager.broadcast(message))
    logger.debug(f"Queued activity broadcast: {activity_data.get('strategy_name')} - {activity_data.get('decision_type')}")
